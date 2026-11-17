export function stopMediaStream(stream) {
  for (const track of stream?.getTracks?.() || []) track.stop();
}

export class CameraSession {
  constructor() {
    this.generation = 0;
    this.stream = null;
  }
  stop() {
    this.generation++;
    stopMediaStream(this.stream);
    this.stream = null;
  }
  async open(request) {
    this.stop();
    const generation = this.generation;
    const stream = await request();
    if (generation !== this.generation) {
      stopMediaStream(stream);
      return null;
    }
    this.stream = stream;
    return stream;
  }
}

export function cameraError(error) {
  if (error?.name === "NotAllowedError")
    return "Camera access was declined. Allow it in your browser settings, or choose a photo instead.";
  if (error?.name === "NotFoundError")
    return "No camera was found. You can upload a photo or enter the plate manually.";
  if (error?.name === "NotReadableError")
    return "The camera is busy in another app. Close that app or choose a photo.";
  return "The camera could not start. Try taking or uploading a photo instead.";
}

export function frameRectangle(
  sourceWidth,
  sourceHeight,
  viewWidth,
  viewHeight,
) {
  if (
    ![sourceWidth, sourceHeight, viewWidth, viewHeight].every(
      (value) => value > 0,
    )
  )
    return null;
  const scale = Math.max(viewWidth / sourceWidth, viewHeight / sourceHeight);
  const left = (sourceWidth - viewWidth / scale) / 2;
  const top = (sourceHeight - viewHeight / scale) / 2;
  return {
    x: left + (viewWidth * 0.08) / scale,
    y: top + (viewHeight * 0.38) / scale,
    width: (viewWidth * 0.84) / scale,
    height: (viewHeight * 0.24) / scale,
  };
}
