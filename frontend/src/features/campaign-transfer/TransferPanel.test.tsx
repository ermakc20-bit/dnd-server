import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { CampaignHome } from "../campaigns/CampaignExperience";
import type { CampaignApi } from "../campaigns/api";
import { TransferError, type TransferApi, type TransferJob } from "./api";

beforeEach(() => sessionStorage.clear());
const campaigns = () => ({ listCampaigns: vi.fn().mockResolvedValue([]), createCampaign: vi.fn() } as unknown as CampaignApi);
function mockApi(): TransferApi {
  return { export: vi.fn(), import: vi.fn().mockRejectedValue(new TransferError("Выберите ZIP кампании до 256 МБ", "archive_limit")),
    get: vi.fn().mockRejectedValue(new TransferError("Задание недоступно", "forbidden")), cancel: vi.fn(), download: vi.fn() };
}

it("rejects a wrong file locally and preserves its actionable error without creating a job", async () => {
  const api = mockApi();
  render(<CampaignHome accessToken="account" api={campaigns()} transferApi={api} />);
  fireEvent.click(await screen.findByRole("button", { name: "Импортировать кампанию" }));
  fireEvent.change(screen.getByLabelText("ZIP кампании"), { target: { files: [new File(["invalid"], "wrong.txt")] } });
  fireEvent.click(screen.getByRole("button", { name: "Восстановить независимую кампанию" }));
  await screen.findByText("Выберите ZIP кампании до 256 МБ");
  expect(api.import).not.toHaveBeenCalled();
  expect(api.get).not.toHaveBeenCalled();
});

it("keeps a completed late cancel result when an older status response arrives", async () => {
  let release!: (state: TransferJob) => void;
  const api = mockApi();
  const state: TransferJob = { id: "transfer-id", kind: "import", phase: "validating", progress: 20,
    cancel_requested: false, result_campaign_id: null, error_code: null, expires_at: "2026-10-14T00:00:00Z", archive_available: false };
  api.import = vi.fn().mockImplementation((id: string) => Promise.resolve({ ...state, id }));
  api.get = vi.fn().mockImplementation(() => new Promise(resolve => { release = resolve; }));
  api.cancel = vi.fn().mockImplementation((id: string) => Promise.resolve({ ...state, id, phase: "completed", progress: 100, result_campaign_id: "copy" }));
  render(<CampaignHome accessToken="account" api={campaigns()} transferApi={api} />);
  fireEvent.click(await screen.findByRole("button", { name: "Импортировать кампанию" }));
  fireEvent.change(screen.getByLabelText("ZIP кампании"), { target: { files: [new File(["ZIP"], "campaign.zip")] } });
  fireEvent.click(screen.getByRole("button", { name: "Восстановить независимую кампанию" }));
  await waitFor(() => expect(api.get).toHaveBeenCalledTimes(1));
  fireEvent.click(screen.getByRole("button", { name: "Отменить перенос" }));
  await screen.findByText(/Создана независимая кампания/);
  release({ ...state, id: vi.mocked(api.get).mock.calls[0][0], phase: "storing", progress: 30 });
  await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Создана независимая кампания"));
  expect(screen.queryByRole("button", { name: "Отменить перенос" })).not.toBeInTheDocument();
});
