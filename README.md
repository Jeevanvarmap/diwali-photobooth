# Diwali photobooth

A local booth for a Mac. It previews a USB webcam, takes 3 portraits with a 10-second countdown before each shot, cuts the guests out, places them on Diwali scenes, and can upload the finished photos to Google Drive.

## Connect the DJI Action 2

1. Use a data USB-C cable, plugged straight into the Mac (not a charge-only cable).
2. Turn the camera on. When it asks how to connect, tap **Webcam**. The screen should say Webcam.
3. In the booth, open **Setup** and choose the camera named **UVC Camera**, **DJI**, or **Action**. If the Action 2 is not listed, click **Refresh cameras**.
4. The built-in laptop camera is the fallback when the Action 2 is unplugged.

macOS will ask for camera permission the first time. Allow it for Terminal (or whichever app you use to start the booth) under System Settings → Privacy & Security → Camera.

Guests should stand in the center of the frame. The Action 2 is very wide, and the booth saves a portrait crop of the middle.

## Run the booth

```bash
cd "/Users/jeevanvarma/Documents/Diwali Photobooth "
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000 and press **Capture**.

Background removal uses rembg when a model file is already on this Mac:

- `~/.rembg/models/u2net/u2net.onnx` (about 176 MB, sharper edges)
- or `~/.rembg/models/u2netp/u2netp.onnx` (about 4 MB)

Download one of those from the [rembg releases](https://github.com/danielgatis/rembg/releases/tag/v0.0.0) if the booth has not fetched it yet. Until a model file is present, the booth still cuts guests out locally so the party can continue. Restart after adding the model file so the next session uses it.

Each guest session is saved on this Mac under `output/YYYY-MM-DD/`.

## Optional AI scenes

Copy `.env.example` to `.env` and set one provider.

- `AI_PROVIDER=openai` and `OPENAI_API_KEY` use the Images edit API. The default model is `gpt-image-1`.
- `AI_PROVIDER=gemini` and `GEMINI_API_KEY` use Gemini image editing. The default model is `gemini-2.5-flash-image`.

Restart the booth after changing `.env`. When a key is present, Setup shows an **AI Diwali scene** switch. Leave it off to skip those calls. The cutout scenes are always made, even if an AI call fails.

## Google Drive

Finished images (not the untouched originals) upload to a folder named `Diwali Photobooth` in the Google account you sign in with.

1. In [Google Cloud Console](https://console.cloud.google.com/), create a project and enable the **Google Drive API**.
2. Create an OAuth client of type **Desktop app**.
3. Download the client JSON and save it as `credentials.json` in this folder.
4. Start the booth and run one session. A browser window opens for a one-time Google sign-in. The token is stored in `token.json`.

The session folder is shared as anyone with the link can view, and the booth shows a QR code. Originals stay on the laptop only.

`credentials.json` and `token.json` are gitignored. Do not share them.
