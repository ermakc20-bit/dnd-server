import { useEffect, useState } from "react";
import { campaignApi, type RoomSummary } from "../features/campaigns/api";

export function RoomRoute({ id, accessToken, onRoom, onBack }: {
  id: string; accessToken: string; onRoom(room: RoomSummary): void; onBack(): void;
}) {
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    setError(null);
    void campaignApi.listCampaigns(accessToken).then(campaigns => {
      if (!active) return;
      const room = campaigns.flatMap(campaign => campaign.rooms).find(room => room.id === id);
      if (room) onRoom(room);
      else setError("Комната недоступна. Проверьте ссылку или попросите мастера о приглашении.");
    }).catch(() => { if (active) setError("Не удалось открыть комнату. Проверьте связь и повторите вход."); });
    return () => { active = false; };
  }, [id, accessToken, onRoom, attempt]);
  return <main className="center-card">
    <h1>{error ? "Стол недоступен" : "Открываем стол…"}</h1>
    {error ? <><p role="alert">{error}</p><button type="button" onClick={() => setAttempt(value => value + 1)}>Повторить вход</button></> : null}
    <button type="button" onClick={onBack}>К кампаниям</button>
  </main>;
}
