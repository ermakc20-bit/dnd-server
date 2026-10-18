import { useState, type FormEvent } from "react";

import { supabase } from "../../lib/supabase";
import "./campaigns.css";
import { safeReturnPath } from "../../routes/productRoute";

export function SignInPanel({ returnTo = "/" }: { returnTo?: string }) {
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!supabase) return;
    const { error } = await supabase.auth.signInWithOtp({
      email,
      options: { emailRedirectTo: `${window.location.origin}${safeReturnPath(returnTo)}` },
    });
    setMessage(error ? "Не удалось отправить ссылку. Проверьте адрес." : "Ссылка для входа отправлена на почту.");
  }

  return (
    <main className="campaign-page campaign-page--center journey-entry">
      <form className="guest-card" onSubmit={submit}>
        <h1>Вход для мастера</h1>
        <p>Мастер входит по почте. Игрокам аккаунт не нужен — достаточно ссылки.</p>
        <label>
          Почта мастера
          <input type="email" value={email} onChange={(event) => setEmail(event.target.value)} required />
        </label>
        <button type="submit">Получить ссылку для входа</button>
        {message ? <p role="status">{message}</p> : null}
      </form>
    </main>
  );
}
