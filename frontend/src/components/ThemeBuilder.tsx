import { useState, useRef, useEffect } from "react";
import { motion } from "framer-motion";
import type { Language } from "../i18n";
import { t } from "../i18n";

const API_BASE = import.meta.env.VITE_API_BASE ?? "";

interface BuildResult {
  theme_name: string;
  display_name: string;
  description: string;
  npc_count: number;
  enemy_count: number;
}

interface Props {
  lang: Language;
  onComplete: () => void;
  onBack: () => void;
}

export default function ThemeBuilder({ lang, onComplete, onBack }: Props) {
  const [authorized, setAuthorized] = useState(false);
  const [password, setPassword] = useState("");
  const [authError, setAuthError] = useState("");

  const [files, setFiles] = useState<File[]>([]);
  const [buildId, setBuildId] = useState("");
  const [themeName, setThemeName] = useState("");
  const [status, setStatus] = useState<"idle" | "uploading" | "building" | "completed" | "error">("idle");
  const [progress, setProgress] = useState(0);
  const [message, setMessage] = useState("");
  const [result, setResult] = useState<BuildResult | null>(null);
  const [error, setError] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);
  const pollRef = useRef<number | null>(null);

  const handleAuth = async () => {
    setAuthError("");
    try {
      const res = await fetch(`${API_BASE}/api/builder/auth`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password }),
      });
      if (res.ok) {
        setAuthorized(true);
      } else {
        setAuthError(t(lang, "builderWrongPassword"));
      }
    } catch {
      setAuthError(t(lang, "builderWrongPassword"));
    }
  };

  useEffect(() => {
    if (buildId && status === "building") {
      pollRef.current = window.setInterval(async () => {
        try {
          const res = await fetch(`${API_BASE}/api/builder/status/${buildId}`);
          const data = await res.json();
          setProgress(data.progress);
          setMessage(data.message);
          if (data.status === "completed") {
            setStatus("completed");
            setResult(data.result);
            if (pollRef.current) clearInterval(pollRef.current);
          } else if (data.status === "error") {
            setStatus("error");
            setError(data.error || data.message);
            if (pollRef.current) clearInterval(pollRef.current);
          }
        } catch { /* ignore */ }
      }, 2000);
    }
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [buildId, status]);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      setFiles(Array.from(e.target.files).filter((f) => f.name.endsWith(".txt")));
    }
  };

  const handleUploadAndBuild = async () => {
    if (files.length === 0) return;
    setStatus("uploading");
    setMessage(t(lang, "uploading"));

    const formData = new FormData();
    files.forEach((f) => formData.append("files", f));

    try {
      const uploadRes = await fetch(`${API_BASE}/api/builder/upload`, { method: "POST", body: formData });
      if (!uploadRes.ok) { const err = await uploadRes.json(); throw new Error(err.detail); }
      const uploadData = await uploadRes.json();
      const id = uploadData.build_id;
      setBuildId(id);

      setStatus("building");
      setMessage(t(lang, "startBuild") + "...");
      setProgress(5);

      const buildRes = await fetch(`${API_BASE}/api/builder/start/${id}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ theme_name: themeName || null }),
      });
      if (!buildRes.ok) { const err = await buildRes.json(); throw new Error(err.detail); }
    } catch (e) {
      setStatus("error");
      setError(e instanceof Error ? e.message : "Unknown error");
    }
  };

  if (!authorized) {
    return (
      <div className="theme-builder">
        <motion.div className="builder-content" initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}>
          <button className="back-btn" onClick={onBack}>{t(lang, "back")}</button>
          <h1 className="builder-title">{t(lang, "builderTitle")}</h1>
          <div className="builder-auth">
            <p className="auth-label">{t(lang, "builderPasswordLabel")}</p>
            <input
              className="auth-input"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleAuth()}
              placeholder={t(lang, "builderPasswordPlaceholder")}
              autoFocus
            />
            {authError && <p className="auth-error">{authError}</p>}
            <motion.button
              className="build-btn"
              onClick={handleAuth}
              disabled={!password}
              whileHover={{ scale: 1.03 }}
              whileTap={{ scale: 0.97 }}
            >
              {t(lang, "builderPasswordSubmit")}
            </motion.button>
          </div>
        </motion.div>
      </div>
    );
  }

  return (
    <div className="theme-builder">
      <motion.div className="builder-content" initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}>
        <button className="back-btn" onClick={onBack}>{t(lang, "back")}</button>
        <h1 className="builder-title">{t(lang, "builderTitle")}</h1>
        <p className="builder-subtitle">{t(lang, "builderSubtitle")}</p>

        {status === "idle" && (
          <div className="builder-form">
            <div className="file-upload-area" onClick={() => fileInputRef.current?.click()}>
              <input ref={fileInputRef} type="file" multiple accept=".txt" onChange={handleFileChange} style={{ display: "none" }} />
              {files.length === 0 ? (
                <div className="upload-placeholder">
                  <span className="upload-icon">📄</span>
                  <p>{t(lang, "selectFiles")}</p>
                  <p className="upload-hint">{t(lang, "selectFilesHint")}</p>
                </div>
              ) : (
                <div className="upload-files">
                  <span className="upload-icon">✅</span>
                  <p>{t(lang, "filesSelected", { n: files.length })}</p>
                  {files.map((f, i) => (
                    <div key={i} className="file-name">{f.name} ({(f.size / 1024).toFixed(1)}KB)</div>
                  ))}
                </div>
              )}
            </div>

            <div className="theme-name-input">
              <label>{t(lang, "themeNameLabel")}</label>
              <input type="text" value={themeName} onChange={(e) => setThemeName(e.target.value)} placeholder={t(lang, "themeNamePlaceholder")} />
            </div>

            <motion.button className="build-btn" onClick={handleUploadAndBuild} disabled={files.length === 0} whileHover={{ scale: 1.03 }} whileTap={{ scale: 0.97 }}>
              {t(lang, "startBuild")}
            </motion.button>
          </div>
        )}

        {(status === "uploading" || status === "building") && (
          <div className="builder-progress">
            <div className="progress-bar-bg">
              <motion.div className="progress-bar-fill" animate={{ width: `${progress}%` }} transition={{ duration: 0.5 }} />
            </div>
            <p className="progress-text">{message}</p>
            <p className="progress-percent">{progress}%</p>
            <motion.div className="building-spinner" animate={{ rotate: 360 }} transition={{ repeat: Infinity, duration: 2, ease: "linear" }}>⚙</motion.div>
          </div>
        )}

        {status === "completed" && result && (
          <motion.div className="builder-result" initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }}>
            <h2>{t(lang, "buildComplete")}</h2>
            <div className="result-card">
              <div className="result-name">{result.display_name}</div>
              <div className="result-desc">{result.description}</div>
              <div className="result-meta">NPC {result.npc_count} · Enemies {result.enemy_count}</div>
            </div>
            <motion.button className="play-new-btn" onClick={onComplete} whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.95 }}>
              {t(lang, "playNewTheme")}
            </motion.button>
          </motion.div>
        )}

        {status === "error" && (
          <div className="builder-error">
            <h2>{t(lang, "buildFailed")}</h2>
            <p>{error}</p>
            <button className="retry-btn" onClick={() => { setStatus("idle"); setError(""); }}>{t(lang, "retry")}</button>
          </div>
        )}
      </motion.div>
    </div>
  );
}
