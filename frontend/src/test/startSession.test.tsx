import { act, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import LoadingScreen from "@/components/common/LoadingScreen";
import { ApiRequestError } from "@/lib/api";
import { startSession } from "@/lib/startSession";

const fast = { delayMs: 0, timeoutMs: 100 };

describe("starting the session", () => {
  it("a stalled or crashed server is retried quietly", async () => {
    const request = vi.fn()
      .mockRejectedValueOnce(new ApiRequestError("timeout", "network_error"))
      .mockRejectedValueOnce(new ApiRequestError("down", "network_error", 502))
      .mockResolvedValueOnce("ok");
    await expect(startSession(request, fast)).resolves.toBe("ok");
    expect(request).toHaveBeenCalledTimes(3);
    expect(request).toHaveBeenCalledWith(100);
  });

  it("a refusal (bad initData, ban) is not retried", async () => {
    const request = vi.fn().mockRejectedValue(new ApiRequestError("no", "unauthorized", 401));
    await expect(startSession(request, fast)).rejects.toThrow("no");
    expect(request).toHaveBeenCalledTimes(1);
  });

  it("gives up after the last attempt with the last error", async () => {
    const request = vi.fn().mockRejectedValue(new ApiRequestError("down", "network_error", 503));
    await expect(startSession(request, { ...fast, attempts: 2 })).rejects.toThrow("down");
    expect(request).toHaveBeenCalledTimes(2);
  });
});

describe("loading screen", () => {
  afterEach(() => vi.useRealTimers());

  it("says it is still working when loading takes long", () => {
    vi.useFakeTimers();
    render(<LoadingScreen />);
    expect(screen.queryByRole("status")).toBeNull();
    act(() => void vi.advanceTimersByTime(5_000));
    expect(screen.getByRole("status")).toHaveTextContent("дольше обычного");
  });
});
