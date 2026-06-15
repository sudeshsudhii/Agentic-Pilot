import { CheckCircle2, Download, Play, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { Settings, updateSettings } from "../api/client";

type Props = {
  settings: Settings;
  onComplete: () => Promise<void>;
};

export function SetupWizard({ settings, onComplete }: Props) {
  const [step, setStep] = useState(1);
  const [status, setStatus] = useState("");

  async function finish() {
    await updateSettings({ setup_complete: true });
    await onComplete();
  }

  return (
    <div className="setup-shell">
      <section className="setup-panel">
        <div className="setup-steps">
          {[1, 2, 3, 4, 5].map((item) => (
            <button className={item === step ? "active" : ""} key={item} onClick={() => setStep(item)}>
              {item}
            </button>
          ))}
        </div>

        {step === 1 ? (
          <div className="setup-content">
            <ShieldCheck size={36} />
            <h1>Pilot</h1>
            <p>Your data never leaves this device. All AI runs locally.</p>
            <button className="primary-button" onClick={() => setStep(2)}>
              Get Started
            </button>
          </div>
        ) : null}

        {step === 2 ? (
          <div className="setup-content">
            <CheckCircle2 size={36} />
            <h1>Ollama</h1>
            <p>{settings.ollama_base_url}</p>
            <button className="primary-button" onClick={() => setStep(3)}>
              Continue
            </button>
          </div>
        ) : null}

        {step === 3 ? (
          <div className="setup-content">
            <Download size={36} />
            <h1>Model</h1>
            <p>{settings.ollama_model}</p>
            <button
              className="primary-button"
              onClick={() => {
                setStatus("Use the backend setup endpoint or run ollama pull qwen2.5:7b.");
                setStep(4);
              }}
            >
              Continue
            </button>
            {status ? <small>{status}</small> : null}
          </div>
        ) : null}

        {step === 4 ? (
          <div className="setup-content">
            <Play size={36} />
            <h1>Test</h1>
            <p>Run a search task from the main screen after setup closes.</p>
            <button className="primary-button" onClick={() => setStep(5)}>
              Continue
            </button>
          </div>
        ) : null}

        {step === 5 ? (
          <div className="setup-content">
            <CheckCircle2 size={36} />
            <h1>Ready</h1>
            <button className="primary-button" onClick={finish}>
              Open Pilot
            </button>
          </div>
        ) : null}
      </section>
    </div>
  );
}
