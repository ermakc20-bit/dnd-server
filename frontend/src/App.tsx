import type { AuthState } from "./auth/useAuthSession";
import { useAuthSession } from "./auth/useAuthSession";
import { VttShell } from "./components/VttShell";

export function AppView({ auth }: { auth: AuthState }) {
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
    return (
      <main className="center-card">
        <span className="panel-label">DnD VTT</span>
        <h1>Быстрый виртуальный стол</h1>
        <p>Войдите через Supabase Auth, чтобы создавать комнаты и открывать сцены.</p>
        <button type="button">Войти</button>
      </main>
    );
  }

  return <VttShell userLabel={auth.session.user.email ?? "Игрок"} />;
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
