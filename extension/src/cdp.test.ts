import { beforeEach, describe, expect, it, vi } from 'vitest';

describe('cdp screenshot safety caps', () => {
  beforeEach(() => {
    vi.resetModules();
  });

  it('caps oversized full-page screenshots before setting device metrics', async () => {
    const sendCommand = vi.fn(async (_target: unknown, method: string) => {
      if (method === 'Page.getLayoutMetrics') {
        return { cssContentSize: { width: 12000, height: 50000 } };
      }
      if (method === 'Page.captureScreenshot') {
        return { data: 'png-data' };
      }
      return {};
    });

    vi.stubGlobal('chrome', {
      tabs: {
        get: vi.fn(async () => ({ id: 7, url: 'https://example.com' })),
        onRemoved: { addListener: vi.fn() },
        onUpdated: { addListener: vi.fn() },
      },
      debugger: {
        attach: vi.fn(async () => {}),
        detach: vi.fn(async () => {}),
        sendCommand,
        onDetach: { addListener: vi.fn() },
      },
    });

    const mod = await import('./cdp');
    const result = await mod.screenshot(7, { fullPage: true });

    expect(result).toBe('png-data');
    expect(sendCommand).toHaveBeenCalledWith(
      { tabId: 7 },
      'Emulation.setDeviceMetricsOverride',
      expect.objectContaining({
        width: 3695,
        height: 10825,
      }),
    );
  });
});
