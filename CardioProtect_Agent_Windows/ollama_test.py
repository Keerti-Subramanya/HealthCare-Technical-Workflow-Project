import subprocess
import json

def query_ollama(prompt: str):
    """Send a quick test prompt to your local Llama3 model."""
    print("🧠 Sending prompt to Ollama...")
    result = subprocess.run(
        ["ollama", "run", "llama3"],
        input=prompt.encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=60
    )
    if result.returncode != 0:
        print("❌ Error:", result.stderr.decode())
        return None
    return result.stdout.decode().strip()

if __name__ == "__main__":
    test_prompt = "Summarize: 316 patients were randomized 1:1 to candesartan or placebo."
    response = query_ollama(test_prompt)
    print("\n🦙 Llama3 response:\n", response or "No response.")
