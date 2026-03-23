import { useState, useEffect } from "react";
import {
  Card,
  Select,
  Button,
  InputNumber,
  Space,
  Divider,
  message,
  Spin,
} from "antd";
import { PlusOutlined, DeleteOutlined } from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import { providerApi } from "../../../../api/modules/provider";
import type { ProviderInfo, ModelSlotConfig } from "../../../../api/types";
import styles from "../index.module.less";

interface ModelConfigCardProps {
  value?: ModelSlotConfig | null;
  onChange?: (value: ModelSlotConfig | null) => void;
  loading?: boolean;
}

interface EligibleProvider {
  id: string;
  name: string;
  models: Array<{ id: string; name: string }>;
}

export function ModelConfigCard({
  value,
  onChange,
  loading = false,
}: ModelConfigCardProps) {
  const { t } = useTranslation();
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [loadingProviders, setLoadingProviders] = useState(false);

  // Fetch providers on mount
  useEffect(() => {
    const fetchProviders = async () => {
      setLoadingProviders(true);
      try {
        const data = await providerApi.listProviders();
        if (Array.isArray(data)) setProviders(data);
      } catch (err) {
        console.error("Failed to load providers", err);
      } finally {
        setLoadingProviders(false);
      }
    };
    fetchProviders();
  }, []);

  // Eligible providers: configured + has models
  const eligibleProviders: EligibleProvider[] = providers
    .filter((p) => {
      const hasModels =
        (p.models?.length ?? 0) + (p.extra_models?.length ?? 0) > 0;
      if (!hasModels) return false;
      if (p.is_local) return true;
      if (p.require_api_key === false) return !!p.base_url;
      if (p.is_custom) return !!p.base_url;
      if (p.require_api_key ?? true) return !!p.api_key;
      return true;
    })
    .map((p) => ({
      id: p.id,
      name: p.name,
      models: [...(p.models ?? []), ...(p.extra_models ?? [])],
    }));

  // Get model options for a provider
  const getModelOptions = (providerId: string) => {
    const provider = eligibleProviders.find((p) => p.id === providerId);
    return provider?.models.map((m) => ({
      label: m.name || m.id,
      value: m.id,
    })) || [];
  };

  // Update a specific model slot (primary or fallback)
  const updateModelSlot = (
    index: number,
    field: keyof ModelSlotConfig,
    fieldValue: unknown,
  ) => {
    if (index === 0) {
      // Updating primary model
      const current = value || { provider_id: "", model: "", fallback_models: [], max_retries: 3 };
      onChange?.({
        ...current,
        [field]: fieldValue,
      });
    } else {
      // Updating fallback model
      const current = value || { provider_id: "", model: "", fallback_models: [], max_retries: 3 };
      const fallbacks = [...(current.fallback_models || [])];
      if (!fallbacks[index - 1]) {
        fallbacks[index - 1] = { provider_id: "", model: "", fallback_models: [], max_retries: 3 };
      }
      fallbacks[index - 1] = {
        ...fallbacks[index - 1],
        [field]: fieldValue,
      };
      onChange?.({
        ...current,
        fallback_models: fallbacks,
      });
    }
  };

  // Remove a fallback model
  const removeFallback = (index: number) => {
    const current = value;
    if (!current?.fallback_models) return;
    const fallbacks = [...current.fallback_models];
    fallbacks.splice(index, 1);
    onChange?.({
      ...current,
      fallback_models: fallbacks,
    });
  };

  // Add a new fallback model
  const addFallback = () => {
    const current = value;
    const fallbacks = [...(current?.fallback_models || [])];
    fallbacks.push({ provider_id: "", model: "", fallback_models: [], max_retries: 3 });
    onChange?.({
      ...current,
      fallback_models: fallbacks,
    });
  };

  const renderModelSlot = (index: number, slot: ModelSlotConfig, isPrimary: boolean) => {
    const providerId = slot.provider_id;
    const modelId = slot.model;
    const maxRetries = slot.max_retries ?? 3;

    return (
      <div key={index} className={styles.modelSlot}>
        <div className={styles.modelSlotHeader}>
          <span className={styles.modelSlotTitle}>
            {isPrimary ? t("agentConfig.primaryModel") : `${t("agentConfig.fallbackModel")} ${index}`}
          </span>
          {!isPrimary && (
            <Button
              type="text"
              danger
              size="small"
              icon={<DeleteOutlined />}
              onClick={() => removeFallback(index - 1)}
            />
          )}
        </div>

        <Space direction="vertical" style={{ width: "100%" }} size="small">
          <div className={styles.modelSelectorRow}>
            <div className={styles.modelSelectorCol}>
              <span className={styles.selectorLabel}>{t("agentConfig.provider")}</span>
              <Select
                value={providerId || undefined}
                placeholder={t("agentConfig.selectProvider")}
                options={eligibleProviders.map((p) => ({
                  label: p.name,
                  value: p.id,
                }))}
                onChange={(val) => updateModelSlot(index, "provider_id", val)}
                style={{ width: "100%" }}
                loading={loadingProviders}
              />
            </div>

            <div className={styles.modelSelectorCol}>
              <span className={styles.selectorLabel}>{t("agentConfig.model")}</span>
              <Select
                value={modelId || undefined}
                placeholder={t("agentConfig.selectModel")}
                options={getModelOptions(providerId)}
                onChange={(val) => updateModelSlot(index, "model", val)}
                style={{ width: "100%" }}
                disabled={!providerId}
              />
            </div>
          </div>

          <div className={styles.retryConfig}>
            <span className={styles.selectorLabel}>{t("agentConfig.maxRetries")}</span>
            <InputNumber
              value={maxRetries}
              min={0}
              max={10}
              onChange={(val) => updateModelSlot(index, "max_retries", val ?? 3)}
              style={{ width: 120 }}
            />
          </div>
        </Space>
      </div>
    );
  };

  if (loading) {
    return (
      <Card className={styles.formCard} title={t("agentConfig.modelConfig")}>
        <div className={styles.spinWrapper}>
          <Spin size="small" />
        </div>
      </Card>
    );
  }

  const current = value || { provider_id: "", model: "", fallback_models: [], max_retries: 3 };
  const fallbacks = current.fallback_models || [];

  return (
    <Card className={styles.formCard} title={t("agentConfig.modelConfig")}>
      <Space direction="vertical" style={{ width: "100%" }} size="middle">
        {/* Primary Model */}
        {renderModelSlot(0, current, true)}

        {/* Fallback Models */}
        {fallbacks.length > 0 && <Divider style={{ margin: 0 }} />}
        {fallbacks.map((fallback, idx) => (
          <div key={idx}>
            {renderModelSlot(idx + 1, fallback, false)}
            {idx < fallbacks.length - 1 && <Divider style={{ margin: "8px 0" }} />}
          </div>
        ))}

        {/* Add Fallback Button */}
        <Button
          type="dashed"
          icon={<PlusOutlined />}
          onClick={addFallback}
          style={{ width: "100%" }}
        >
          {t("agentConfig.addFallbackModel")}
        </Button>
      </Space>
    </Card>
  );
}
