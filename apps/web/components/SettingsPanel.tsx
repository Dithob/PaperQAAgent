"use client";

import { CheckCircle2, KeyRound, Loader2, Settings, XCircle } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { getLlmProviderTemplates, testLlmConfig } from "../lib/api";
import type { LLMConfig, LLMProviderId, LLMProviderTemplate } from "../lib/types";

const STORAGE_KEY = "qaagent.llmConfig.v1";

type Props = {
  open: boolean;
  onClose: () => void;
  onConfigChange: (config: LLMConfig | null) => void;
  onNotice: (message: string) => void;
};

export function SettingsPanel({ open, onClose, onConfigChange, onNotice }: Props) {
  const [templates, setTemplates] = useState<LLMProviderTemplate[]>([]);
  const [config, setConfig] = useState<LLMConfig | null>(null);
  const [testing, setTesting] = useState(false);

  useEffect(() => {
    const saved = loadSavedConfig();
    if (saved) {
      setConfig(saved);
    }
    getLlmProviderTemplates()
      .then((items) => {
        setTemplates(items);
        if (!saved && items[0]) {
          const initial = configFromTemplate(items[0]);
          setConfig(initial);
          onConfigChange(null);
        } else if (saved) {
          onConfigChange(isUsable(saved, items) ? saved : null);
        }
      })
      .catch((error) => onNotice(error instanceof Error ? error.message : "Failed to load LLM providers."));
  }, [onConfigChange, onNotice]);

  const template = useMemo(
    () => templates.find((item) => item.id === config?.provider) || templates[0],
    [templates, config?.provider]
  );
  const usable = config ? isUsable(config, templates) : false;

  function updateConfig(next: LLMConfig) {
    setConfig(next);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    onConfigChange(isUsable(next, templates) ? next : null);
  }

  function handleProviderChange(provider: LLMProviderId) {
    const nextTemplate = templates.find((item) => item.id === provider);
    if (!nextTemplate) return;
    updateConfig(configFromTemplate(nextTemplate, config?.api_key || ""));
  }

  async function handleTest() {
    if (!config) return;
    setTesting(true);
    try {
      const result = await testLlmConfig(config);
      onNotice(result.ok ? `LLM connected: ${result.message}` : `LLM test failed: ${result.message}`);
    } catch (error) {
      onNotice(error instanceof Error ? error.message : "LLM test failed.");
    } finally {
      setTesting(false);
    }
  }

  if (!open) return null;

  return (
    <div className="settings-overlay">
      <section className="settings-panel">
        <div className="settings-header">
          <div className="brand">
            <div className="brand-mark"><Settings size={17} /></div>
            LLM Settings
          </div>
          <button className="icon-button secondary-button" title="Close settings" onClick={onClose}>
            <XCircle size={18} />
          </button>
        </div>

        {config && template ? (
          <div className="settings-body">
            <label className="field-label">
              Provider
              <select className="select" value={config.provider} onChange={(event) => handleProviderChange(event.target.value as LLMProviderId)}>
                {templates.map((item) => (
                  <option value={item.id} key={item.id}>{item.label}</option>
                ))}
              </select>
            </label>

            <label className="field-label">
              Model
              <select className="select" value={config.model} onChange={(event) => updateConfig({ ...config, model: event.target.value })}>
                {template.models.map((model) => (
                  <option value={model.id} key={model.id}>{model.label}</option>
                ))}
                {!template.models.some((model) => model.id === config.model) ? <option value={config.model}>{config.model}</option> : null}
              </select>
            </label>

            <label className="field-label">
              Custom model
              <input className="field" value={config.model} onChange={(event) => updateConfig({ ...config, model: event.target.value })} />
            </label>

            <label className="field-label">
              Base URL
              <input
                className="field"
                value={config.base_url || ""}
                onChange={(event) => updateConfig({ ...config, base_url: event.target.value })}
                disabled={!template.supports_custom_base_url && config.provider !== "azure_openai"}
              />
            </label>

            {config.provider === "azure_openai" ? (
              <label className="field-label">
                API version
                <input className="field" value={config.api_version || ""} onChange={(event) => updateConfig({ ...config, api_version: event.target.value })} />
              </label>
            ) : null}

            <label className="field-label">
              {template.api_key_label}
              <input
                className="field"
                type="password"
                value={config.api_key || ""}
                onChange={(event) => updateConfig({ ...config, api_key: event.target.value })}
                placeholder={template.api_key_required ? "Required" : "Optional"}
              />
            </label>

            <div className="control-grid">
              <label className="field-label">
                Temperature
                <input
                  className="field"
                  type="number"
                  min="0"
                  max="2"
                  step="0.1"
                  value={config.options.temperature}
                  onChange={(event) => updateConfig({ ...config, options: { ...config.options, temperature: Number(event.target.value) } })}
                />
              </label>
              <label className="field-label">
                Max tokens
                <input
                  className="field"
                  type="number"
                  min="128"
                  max="8000"
                  step="128"
                  value={config.options.max_tokens}
                  onChange={(event) => updateConfig({ ...config, options: { ...config.options, max_tokens: Number(event.target.value) } })}
                />
              </label>
            </div>

            <div className={`settings-state ${usable ? "ok" : "idle"}`}>
              {usable ? <CheckCircle2 size={16} /> : <KeyRound size={16} />}
              {usable ? `${template.label} / ${config.model}` : "Local fallback is active"}
            </div>

            <button className="primary-button" onClick={handleTest} disabled={!usable || testing}>
              {testing ? <Loader2 size={16} /> : <CheckCircle2 size={16} />}
              Test
            </button>
          </div>
        ) : (
          <div className="settings-body">
            <div className="settings-state idle"><Loader2 size={16} /> Loading providers</div>
          </div>
        )}
      </section>
    </div>
  );
}

function configFromTemplate(template: LLMProviderTemplate, apiKey = ""): LLMConfig {
  return {
    provider: template.id,
    model: template.default_model,
    api_key: template.api_key_required ? apiKey : "",
    base_url: template.base_url || "",
    api_version: template.id === "azure_openai" ? "2024-02-15-preview" : "",
    options: {
      temperature: 0.1,
      max_tokens: 900
    }
  };
}

function isUsable(config: LLMConfig, templates: LLMProviderTemplate[]) {
  const template = templates.find((item) => item.id === config.provider);
  if (!template) return false;
  if (!config.model) return false;
  if (template.api_key_required && !config.api_key) return false;
  if ((template.supports_custom_base_url || config.provider === "azure_openai") && !config.base_url) return false;
  return true;
}

function loadSavedConfig(): LLMConfig | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) as LLMConfig : null;
  } catch {
    return null;
  }
}
