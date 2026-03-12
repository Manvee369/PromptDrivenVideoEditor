from fastapi import FastAPI
from app.video_processing import remove_silence
from moviepy.editor import VideoFileClip, vfx

app = FastAPI()
PROCESSED_FOLDER = "processed"

@app.post("/generate")
def generate_video(filename: str, prompt: str):

    input_path = f"uploads/{filename}"
    output_path = f"processed/edited_{filename}"

    clip = VideoFileClip(input_path)

    # Simple prompt logic
    if "short" in prompt:
        clip = clip.subclip(0, 5)

    if "black and white" in prompt:
        clip = clip.fx(vfx.blackwhite)

    if "slow motion" in prompt:
        clip = clip.fx(vfx.speedx, 0.5)

    clip.write_videofile(output_path)

    return {
        "status": "processed",
        "output": output_path
    }
    
@app.post("/remove-silence")
def process_video(filename: str):

    input_path = f"uploads/{filename}"
    output_path = f"processed/nosilence_{filename}"

    remove_silence(input_path, output_path)

    return {
        "status": "done",
        "output": output_path
    }