import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";

import EmbySettingsDialog from "../EmbySettingsDialog";
import { toast } from "@/components/ui/toast";
import * as configApi from "@/api/config";
import type { EmbyConfig } from "@/types/beets-config";

vi.mock("@/api/config", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/config")>();
  return { ...actual, testEmbyConnection: vi.fn() };
});

const mockedTest = vi.mocked(configApi.testEmbyConnection);

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}

const validConfig: EmbyConfig = {
  host: "192.168.1.50",
  port: 8096,
  userid: "user123",
  apikey: "key123",
};

function renderDialog(overrides: Partial<EmbyConfig> = {}) {
  const onSave = vi.fn();
  render(
    <EmbySettingsDialog
      open
      onOpenChange={() => {}}
      config={{ ...validConfig, ...overrides }}
      libraryId={1}
      onSave={onSave}
    />,
    { wrapper: createWrapper() },
  );
  return { onSave };
}

describe("EmbySettingsDialog test-on-save", () => {
  beforeEach(() => {
    mockedTest.mockReset();
    vi.restoreAllMocks();
  });

  it("saves and warns via toast when the on-save connection test fails", async () => {
    const user = userEvent.setup();
    const warnSpy = vi.spyOn(toast, "warning");
    mockedTest.mockResolvedValue({
      success: false,
      message: "Connection refused",
    });

    const { onSave } = renderDialog();
    await user.click(screen.getByRole("button", { name: "Apply" }));

    // Save proceeds immediately, regardless of the test outcome.
    expect(onSave).toHaveBeenCalledWith(validConfig);

    await waitFor(() => expect(warnSpy).toHaveBeenCalledTimes(1));
    expect(warnSpy.mock.calls[0][0].description).toContain("192.168.1.50:8096");
    expect(warnSpy.mock.calls[0][0].description).toContain(
      "Connection refused",
    );
    expect(mockedTest).toHaveBeenCalledTimes(1);
  });

  it("saves silently when the on-save connection test succeeds", async () => {
    const user = userEvent.setup();
    const warnSpy = vi.spyOn(toast, "warning");
    mockedTest.mockResolvedValue({
      success: true,
      message: "Connected",
      server_name: "Emby",
      server_version: "4.8",
    });

    const { onSave } = renderDialog();
    await user.click(screen.getByRole("button", { name: "Apply" }));

    expect(onSave).toHaveBeenCalledWith(validConfig);
    await waitFor(() => expect(mockedTest).toHaveBeenCalledTimes(1));
    expect(warnSpy).not.toHaveBeenCalled();
  });

  it("skips the on-save test when the same credentials were already verified manually", async () => {
    const user = userEvent.setup();
    const warnSpy = vi.spyOn(toast, "warning");
    mockedTest.mockResolvedValue({
      success: true,
      message: "Connected",
      server_name: "Emby",
      server_version: "4.8",
    });

    renderDialog();

    // Manual test first → marks these credentials as verified.
    await user.click(screen.getByRole("button", { name: "Test Connection" }));
    await waitFor(() => expect(mockedTest).toHaveBeenCalledTimes(1));

    // Saving the unchanged config must not re-run the test.
    await user.click(screen.getByRole("button", { name: "Apply" }));
    expect(mockedTest).toHaveBeenCalledTimes(1);
    expect(warnSpy).not.toHaveBeenCalled();
  });

  it("does not run the on-save test when credentials are incomplete", async () => {
    const user = userEvent.setup();
    const warnSpy = vi.spyOn(toast, "warning");

    const { onSave } = renderDialog({ apikey: "" });
    await user.click(screen.getByRole("button", { name: "Apply" }));

    expect(onSave).toHaveBeenCalled();
    expect(mockedTest).not.toHaveBeenCalled();
    expect(warnSpy).not.toHaveBeenCalled();
  });
});
