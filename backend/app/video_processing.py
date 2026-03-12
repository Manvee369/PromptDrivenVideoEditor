import subprocess

def remove_silence(input_file, output_file):

    command = [
        "ffmpeg",
        "-i", input_file,
        "-af", "silenceremove=start_periods=1:start_silence=0.3:start_threshold=-40dB",
        output_file
    ]

    subprocess.run(command)