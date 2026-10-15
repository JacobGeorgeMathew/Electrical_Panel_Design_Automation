import { describe, expect, it } from 'vitest';
import { fitPanelCamera } from './cameraFit';

describe('fitPanelCamera', () => {
  const bounds = { width: 6, height: 8, depth: 3 };

  it('centers the camera target on the selected enclosure', () => {
    expect(fitPanelCamera(bounds, 16 / 9).center).toEqual([3, 4, 1.5]);
  });

  it('backs the camera away for a narrow viewport so the model remains framed', () => {
    const wide = fitPanelCamera(bounds, 16 / 9);
    const narrow = fitPanelCamera(bounds, 9 / 16);
    const distance = (pose: typeof wide) => Math.hypot(
      pose.position[0] - pose.center[0], pose.position[1] - pose.center[1], pose.position[2] - pose.center[2],
    );
    expect(distance(narrow)).toBeGreaterThan(distance(wide));
  });
});
