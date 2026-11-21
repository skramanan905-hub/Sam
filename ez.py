import os
import shutil
import uuid
import asyncio
from typing import Optional
from fastapi import FastAPI, BackgroundTasks, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Initialize App
app = FastAPI()

# Enable CORS for frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Change to your frontend domain in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create a folder to store temporary uploaded images if it doesn't exist
UPLOAD_DIR = "temp_uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)
# Serve the uploaded files so the frontend can access them
app.mount("/ai-demo/gen-temp", StaticFiles(directory=UPLOAD_DIR), name="static")

# Dummy Database to hold our task statuses
tasks_db = {}


# ==========================================
# PYDANTIC MODELS (Matching your log data)
# ==========================================
class InputData(BaseModel):
    scene: str = "ezmaker-v1"
    prompt: str = ""
    duration: int = 4
    resolution: str = "540p"
    source_image: Optional[str] = ""  # Will be empty for Text-to-Video, filled for Image-to-Video

class CreateRequest(BaseModel):
    fn_name: str
    call_type: int
    input: InputData
    request_from: Optional[int] = 37
    origin_from: Optional[str] = ""

class StatusRequest(BaseModel):
    task_id: str
    fn_name: str = "demo-ai-video-generator"
    call_type: int = 2
    consume_type: int = -1
    request_from: int = 37
    origin_from: str = ""


# ==========================================
# BACKGROUND VIDEO GENERATOR LOGIC
# ==========================================
async def generate_video_task(task_id: str, prompt: str, source_image: str):
    """
    This is where your actual AI generation or Browser automation will happen.
    Because it is a background task, Render's 30-second limit won't kill the request!
    """
    if source_image:
        print(f"[Task {task_id}] Starting IMAGE-TO-VIDEO generation.")
        print(f"Image URL: {source_image} | Prompt: {prompt}")
    else:
        print(f"[Task {task_id}] Starting TEXT-TO-VIDEO generation.")
        print(f"Prompt: {prompt}")

    # Simulate heavy processing (e.g., your browser automation taking time)
    await asyncio.sleep(15) 

    # When done, update the database with the final MP4 URL
    tasks_db[task_id] = {
        "status": 2, # 2 = Completed
        "result_url": "https://www.w3schools.com/html/mov_bbb.mp4" # Replace with your actual generated video URL
    }
    print(f"[Task {task_id}] Video generation complete!")


# ==========================================
# ENDPOINT 1: UPLOAD IMAGE (For Image-to-Video)
# ==========================================
@app.post("/api/v1/aikit/upload-oss-file")
async def upload_file(file: UploadFile = File(...)):
    # Create a unique filename
    file_extension = file.filename.split(".")[-1]
    unique_filename = f"raw_{uuid.uuid4().hex}.{file_extension}"
    file_path = os.path.join(UPLOAD_DIR, unique_filename)

    # Save the file to our temp folder
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # Return the exact JSON structure your log expects
    return {
        "code": 200,
        "message": "success",
        "data": {
            "url": f"ai-demo/gen-temp/{unique_filename}"
        }
    }


# ==========================================
# ENDPOINT 2: CREATE TASK
# ==========================================
@app.post("/api/v1/aikit/create")
async def create_task(request: CreateRequest, background_tasks: BackgroundTasks):
    task_id = str(uuid.uuid4())
    
    # Save the initial status in our "database"
    tasks_db[task_id] = {"status": 0, "result_url": ""} # 0 = Processing
    
    # Send the job to the background
    background_tasks.add_task(
        generate_video_task, 
        task_id=task_id, 
        prompt=request.input.prompt, 
        source_image=request.input.source_image
    )
    
    # Immediately return the task ID to the frontend
    return {
        "code": 200,
        "message": "success",
        "data": {
            "points_type": -1,
            "task_id": task_id,
            "queue_len": 0,
            "rank": 0,
            "consume_points": 0,
            "call_type": request.call_type
        }
    }


# ==========================================
# ENDPOINT 3: CHECK STATUS
# ==========================================
@app.post("/api/v1/aikit/check-status")
async def check_status(request: StatusRequest):
    task = tasks_db.get(request.task_id)
    
    if not task:
        return {"code": 404, "message": "Task not found"}
    
    # If the video is still generating (Status 0)
    if task["status"] == 0:
        return {
            "code": 200,
            "message": "success",
            "data": {
                "status": 0,
                "fn_name": request.fn_name
            }
        }
    
    # If the video is finished (Status 2)
    return {
        "code": 200,
        "message": "success",
        "data": {
            "status": 2,
            "fn_name": request.fn_name,
            "error": "",
            "result_image": task["result_url"] # Note: EZMaker calls the video URL 'result_image'
        }
    }

# Run the app locally for testing
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
