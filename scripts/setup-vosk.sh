#!/bin/bash
# Setup script to download Vosk model for wake word detection

MODEL_DIR="vosk-model"
MODEL_NAME="vosk-model-small-en-us-0.15"
MODEL_URL="https://alphacephei.com/vosk/models/${MODEL_NAME}.zip"

echo "Downloading Vosk model for wake word detection..."

mkdir -p "$MODEL_DIR"
cd "$MODEL_DIR"

if [ -d "$MODEL_NAME" ]; then
    echo "Model already exists at $MODEL_DIR/$MODEL_NAME"
    exit 0
fi

wget -q "$MODEL_URL" || { echo "Failed to download model"; exit 1; }
unzip -q "${MODEL_NAME}.zip" || { echo "Failed to extract model"; exit 1; }
rm "${MODEL_NAME}.zip"

echo "Model downloaded successfully to $MODEL_DIR/$MODEL_NAME"
echo ""
echo "For production builds, the model is included automatically via GitHub Actions."