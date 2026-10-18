import { useCallback, useEffect, useState } from "react";

import type { AuthState } from "./auth/useAuthSession";
import { useAuthSession } from "./auth/useAuthSession";
import { VttShell } from "./components/VttShell";
import { CampaignHome, GuestJoin } from "./features/campaigns/CampaignExperience";
import { SignInPanel } from "./features/campaigns/SignInPanel";
import type { GuestSession, RoomSummary } from "./features/campaigns/api";
import { SceneExperience } from "./features/scene/SceneExperience";
import { RoomRoute } from "./routes/RoomRoute";
import { useProductRoute } from "./routes/productRoute";

export function AppView({ auth }: { auth: AuthState }) {
  const { route, path, navigate } = useProductRoute();
  useEffect(() => {
    document.title = route.kind === "room" ? "Игровой стол" : route.kind === "join" ? "Вход в комнату" : "Кампании";
  }, [route.kind]);
  const scope = `${auth.status}:${auth.session?.access_token ?? ""}:${path}`;
  const [opened, setOpened] = useState<{ room: RoomSummary; scope: string } | null>(null);
  const onSession = useCallback((session: GuestSession) => setOpened({ room: session.room, scope }), [scope]);
  const onRoom = useCallback((room: RoomSummary) => setOpened({ room, scope }), [scope]);
  const back = () => { setOpened(null); navigate("/"); };
  if (route.kind === "missing") return <main className="center-card"><h1>Страница не найдена</h1>
    <p>Проверьте адрес или откройте свои кампании.</p><button type="button" onClick={back}>К кампаниям</button></main>;
  if (opened?.scope === scope && (route.kind === "join" || auth.status === "authenticated" && route.kind === "room")) {
    return <SceneExperience key={opened.room.id} room={opened.room}
      accessToken={auth.status === "authenticated" ? auth.session.access_token : undefined}
      onBack={route.kind === "join" ? undefined : back} />;
  }
  if (route.kind === "join") {
    return (
      <GuestJoin
        inviteToken={route.token}
        accessToken={auth.status === "authenticated" ? auth.session.access_token : undefined}
        onSession={onSession}
      />
    );
  }
  if (auth.status === "loading") {
    return <main className="center-card">Проверяем сессию…</main>;
  }

  if (auth.status === "misconfigured") {
    return (
      <main className="center-card center-card--warning">
        <span className="panel-label">Локальная настройка</span>
        <h1>Supabase ещё не подключён</h1>
        <p>Скопируйте `.env.example` в `.env` и задайте публичные Vite-переменные.</p>
      </main>
    );
  }

  if (auth.status === "anonymous") {
    return <SignInPanel returnTo={path} />;
  }

  if (route.kind === "room") return <RoomRoute id={route.id} accessToken={auth.session.access_token} onRoom={onRoom} onBack={back} />;
  return <CampaignHome accessToken={auth.session.access_token} onOpenRoom={room => {
    const next = `/rooms/${encodeURIComponent(room.id)}`;
    setOpened({ room, scope: `${auth.status}:${auth.session.access_token}:${next}` }); navigate(next);
  }} />;
}

export default function App() {
  if (
    import.meta.env.DEV
    && new URLSearchParams(window.location.search).get("preview") === "workspace"
  ) {
    return <VttShell userLabel="Гейм-мастер" />;
  }

  return <AppView auth={useAuthSession()} />;
}
