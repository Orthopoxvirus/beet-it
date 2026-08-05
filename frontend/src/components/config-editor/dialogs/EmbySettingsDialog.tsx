import { useState, useEffect } from "react";
import { Loader2, CheckCircle2, XCircle } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "@/components/ui/toast";
import { useTestEmbyConnection } from "@/hooks/useConfig";
import type { EmbyConfig } from "@/types/beets-config";
import PluginSettingsDialog from "./PluginSettingsDialog";

/** Stable identity for a set of Emby credentials, used to skip a redundant
 *  on-save test when the same values were already verified manually. */
function credKey(config: EmbyConfig): string {
  return `${config.host}|${config.port}|${config.userid}|${config.apikey}`;
}

interface EmbySettingsDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  config: EmbyConfig;
  libraryId: number;
  onSave: (config: EmbyConfig) => void;
}

export default function EmbySettingsDialog({
  open,
  onOpenChange,
  config,
  libraryId,
  onSave,
}: EmbySettingsDialogProps) {
  const [localConfig, setLocalConfig] = useState<EmbyConfig>(config);
  const [testResult, setTestResult] = useState<{
    success: boolean;
    message: string;
    serverName?: string;
    serverVersion?: string;
  } | null>(null);

  // Credentials whose connection was last verified green via the Test button,
  // so an identical on-save test can be skipped.
  const [verifiedKey, setVerifiedKey] = useState<string | null>(null);

  const testConnectionMutation = useTestEmbyConnection();

  // Reset local state when dialog opens
  useEffect(() => {
    if (open) {
      setLocalConfig(config);
      setTestResult(null);
      setVerifiedKey(null);
    }
  }, [open, config]);

  const isComplete = (c: EmbyConfig) =>
    Boolean(c.host && c.port && c.userid && c.apikey);

  const handleSave = () => {
    // Persist immediately — the dialog closes and saving is never blocked.
    onSave(localConfig);

    // Fire-and-forget connection check; warn (don't block) if it fails. Skip
    // when fields are incomplete or these exact credentials already tested green.
    if (!isComplete(localConfig)) return;
    if (verifiedKey === credKey(localConfig)) return;
    void runSaveConnectionCheck(localConfig);
  };

  const runSaveConnectionCheck = async (cfg: EmbyConfig) => {
    const target = `${cfg.host}:${cfg.port}`;
    try {
      const result = await testConnectionMutation.mutateAsync({
        libraryId,
        credentials: {
          host: cfg.host,
          port: cfg.port,
          userid: cfg.userid,
          apikey: cfg.apikey,
        },
      });
      if (!result.success) {
        toast.warning({
          title: "Emby not reachable",
          description: `Emby at ${target} could not be reached — settings saved, but the library refresh will fail. (${result.message})`,
        });
      }
    } catch (error) {
      const detail =
        error instanceof Error ? error.message : "connection test failed";
      toast.warning({
        title: "Emby not reachable",
        description: `Emby at ${target} could not be reached — settings saved, but the library refresh will fail. (${detail})`,
      });
    }
  };

  const handleCancel = () => {
    setLocalConfig(config);
  };

  const handleTestConnection = async () => {
    setTestResult(null);
    try {
      const result = await testConnectionMutation.mutateAsync({
        libraryId,
        credentials: {
          host: localConfig.host,
          port: localConfig.port,
          userid: localConfig.userid,
          apikey: localConfig.apikey,
        },
      });
      setTestResult(result);
      setVerifiedKey(result.success ? credKey(localConfig) : null);
    } catch (error) {
      setTestResult({
        success: false,
        message:
          error instanceof Error ? error.message : "Connection test failed",
      });
      setVerifiedKey(null);
    }
  };

  const isTestDisabled = !isComplete(localConfig);

  return (
    <PluginSettingsDialog
      open={open}
      onOpenChange={onOpenChange}
      pluginName="embyupdate"
      onSave={handleSave}
      onCancel={handleCancel}
    >
      {/* Host and Port */}
      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-2">
          <Label htmlFor="emby-host">Host</Label>
          <Input
            id="emby-host"
            value={localConfig.host}
            onChange={(e) =>
              setLocalConfig({ ...localConfig, host: e.target.value })
            }
            placeholder="192.168.1.100 or emby.local"
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor="emby-port">Port</Label>
          <Input
            id="emby-port"
            type="number"
            min={1}
            max={65535}
            value={localConfig.port}
            onChange={(e) =>
              setLocalConfig({
                ...localConfig,
                port: parseInt(e.target.value) || 8096,
              })
            }
            placeholder="8096"
          />
        </div>
      </div>

      {/* User ID */}
      <div className="space-y-2">
        <Label htmlFor="emby-userid">User ID</Label>
        <p className="text-xs text-muted-foreground">
          The Emby user ID (found in Emby server settings)
        </p>
        <Input
          id="emby-userid"
          value={localConfig.userid}
          onChange={(e) =>
            setLocalConfig({ ...localConfig, userid: e.target.value })
          }
          placeholder="abc123def456..."
          className="font-mono text-sm"
        />
      </div>

      {/* API Key */}
      <div className="space-y-2">
        <Label htmlFor="emby-apikey">API Key</Label>
        <p className="text-xs text-muted-foreground">
          Generate an API key in Emby server settings
        </p>
        <Input
          id="emby-apikey"
          type="password"
          value={localConfig.apikey}
          onChange={(e) =>
            setLocalConfig({ ...localConfig, apikey: e.target.value })
          }
          placeholder="Your Emby API key"
          className="font-mono text-sm"
        />
      </div>

      {/* Test Connection */}
      <div className="flex items-center gap-4 pt-2">
        <Button
          type="button"
          variant="outline"
          onClick={handleTestConnection}
          disabled={isTestDisabled || testConnectionMutation.isPending}
        >
          {testConnectionMutation.isPending && (
            <Loader2 className="h-4 w-4 mr-2 animate-spin" />
          )}
          Test Connection
        </Button>

        {testResult && (
          <div
            className={`flex items-center gap-2 text-sm ${
              testResult.success ? "text-green-600" : "text-destructive"
            }`}
          >
            {testResult.success ? (
              <>
                <CheckCircle2 className="h-4 w-4" />
                <span>
                  Connected to {testResult.serverName} (v
                  {testResult.serverVersion})
                </span>
              </>
            ) : (
              <>
                <XCircle className="h-4 w-4" />
                <span>{testResult.message}</span>
              </>
            )}
          </div>
        )}
      </div>
    </PluginSettingsDialog>
  );
}
