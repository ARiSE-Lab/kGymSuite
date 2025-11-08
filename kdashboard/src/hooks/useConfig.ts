import { useState, useEffect } from 'react';

export interface AppConfig {
  kGymAPIEndpoint: string;
}

interface UseConfigResult {
  config: AppConfig | null;
  loading: boolean;
  error: string | null;
}

export function useConfig(): UseConfigResult {
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchConfig = async () => {
      try {
        setLoading(true);
        setError(null);

        const response = await fetch('/config.json');
        if (!response.ok) {
          throw new Error(`Failed to load configuration: ${response.status}`);
        }

        const configData = await response.json();

        // Validate required fields
        if (!configData.kGymAPIEndpoint) {
          throw new Error('Configuration missing required field: kGymAPIEndpoint');
        }

        setConfig(configData);
      } catch (err) {
        const errorMessage = err instanceof Error ? err.message : 'Unknown error loading configuration';
        setError(errorMessage);
        console.error('Configuration loading error:', err);
      } finally {
        setLoading(false);
      }
    };

    fetchConfig();
  }, []);

  return { config, loading, error };
}