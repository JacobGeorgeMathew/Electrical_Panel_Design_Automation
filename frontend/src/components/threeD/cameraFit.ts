export type PanelBounds = { width: number; height: number; depth: number };
export type CameraFit = { center: [number, number, number]; position: [number, number, number] };

/** Return a perspective camera pose that fits the enclosure at the current viewport aspect. */
export function fitPanelCamera(
  bounds: PanelBounds,
  aspect: number,
  fovDegrees = 45,
  margin = 1.2,
): CameraFit {
  const safeAspect = Math.max(aspect, 0.01);
  const center: [number, number, number] = [bounds.width / 2, bounds.height / 2, bounds.depth / 2];
  const radius = Math.sqrt(bounds.width ** 2 + bounds.height ** 2 + bounds.depth ** 2) / 2;
  const verticalHalfFov = (fovDegrees * Math.PI) / 360;
  const horizontalHalfFov = Math.atan(Math.tan(verticalHalfFov) * safeAspect);
  const distance = (radius / Math.sin(Math.min(verticalHalfFov, horizontalHalfFov))) * margin;
  const directionLength = Math.sqrt(1 ** 2 + 0.7 ** 2 + 1.5 ** 2);
  const direction: [number, number, number] = [1 / directionLength, 0.7 / directionLength, 1.5 / directionLength];

  return {
    center,
    position: [
      center[0] + direction[0] * distance,
      center[1] + direction[1] * distance,
      center[2] + direction[2] * distance,
    ],
  };
}
