import { useState, useEffect, useCallback } from "react";
import api from "../../../api";
import type { WorkspaceRestrictionConfig } from "../../../api/modules/security";

const DEFAULT_CONFIG: WorkspaceRestrictionConfig = {
  enabled: false,
  allow_patterns: [],
};

export function useWorkspaceRestriction() {
  const [config, setConfig] =
    useState<WorkspaceRestrictionConfig>(DEFAULT_CONFIG);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchConfig = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getWorkspaceRestriction();
      setConfig(data);
    } catch (err) {
      const errMsg =
        err instanceof Error
          ? err.message
          : "Failed to load workspace restriction config";
      setError(errMsg);
    } finally {
      setLoading(false);
    }
  }, []);

  const updateConfig = useCallback(
    async (newConfig: WorkspaceRestrictionConfig) => {
      try {
        const data = await api.updateWorkspaceRestriction(newConfig);
        setConfig(data);
        return true;
      } catch (err) {
        throw err;
      }
    },
    [],
  );

  useEffect(() => {
    fetchConfig();
  }, [fetchConfig]);

  return {
    config,
    setConfig,
    loading,
    error,
    fetchConfig,
    updateConfig,
  };
}
