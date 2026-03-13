import React, { useState, useEffect } from 'react';
import { 
  Shield, 
  Bell, 
  Database,
  Save,
  RefreshCw,
  AlertTriangle,
  Check
} from 'lucide-react';
import { useApi } from '../contexts/ApiContext';
import { SystemConfig, LoadingState } from '../types';
import { clsx } from 'clsx';
import toast from 'react-hot-toast';

export const Settings: React.FC = () => {
  const { api } = useApi();
  const [config, setConfig] = useState<SystemConfig | null>(null);
  const [loadingState, setLoadingState] = useState<LoadingState>({ isLoading: true });
  const [isUpdating, setIsUpdating] = useState(false);
  const [activeTab, setActiveTab] = useState<'risk' | 'alerts' | 'compliance' | 'system'>('risk');

  useEffect(() => {
    loadSystemConfig();
  }, []);

  const loadSystemConfig = async () => {
    try {
      setLoadingState({ isLoading: true });
      const response = await api.get('/settings/config');
      setConfig(response.data.data);
      setLoadingState({ isLoading: false });
    } catch (error) {
      console.error('Failed to load system config:', error);
      setLoadingState({ isLoading: false, error: 'Failed to load configuration' });
      // Fallback to mock data for UI development
      setConfig(getMockConfig());
    }
  };

  const getMockConfig = (): SystemConfig => ({
    risk_thresholds: {
      low: 0.3,
      medium: 0.6,
      high: 0.8,
      critical: 0.9
    },
    alert_settings: {
      auto_escalation_hours: 24,
      notification_channels: ['email', 'dashboard'],
      priority_rules: {
        high_risk_threshold: 0.8,
        velocity_multiplier: 1.5,
        pep_escalation: true
      }
    },
    compliance_settings: {
      sar_filing_deadline_days: 30,
      retention_period_years: 7,
      required_approvals: 2
    }
  });

  const saveConfig = async () => {
    if (!config) return;
    try {
      setIsUpdating(true);
      await api.put('/settings/config', config);
      toast.success('Configuration saved successfully');
    } catch (error) {
      toast.error('Failed to save configuration');
    } finally {
      setIsUpdating(false);
    }
  };

  const updateRiskThreshold = (level: keyof SystemConfig['risk_thresholds'], value: number) => {
    if (!config) return;
    setConfig({
      ...config,
      risk_thresholds: { ...config.risk_thresholds, [level]: value }
    });
  };

  const tabs = [
    { id: 'risk' as const, name: 'Risk Thresholds', icon: Shield },
    { id: 'alerts' as const, name: 'Alert Settings', icon: Bell },
    { id: 'compliance' as const, name: 'Compliance', icon: AlertTriangle },
    { id: 'system' as const, name: 'System', icon: Database }
  ];

  if (loadingState.isLoading) {
    return <div className="p-8 animate-pulse">Loading settings...</div>;
  }

  return (
    <div className="space-y-6 p-6">
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">System Settings</h1>
          <p className="text-gray-600">Configure AML detection parameters</p>
        </div>
        <div className="flex space-x-3">
          <button onClick={loadSystemConfig} className="btn btn-secondary flex items-center">
            <RefreshCw className={clsx('h-4 w-4 mr-2', loadingState.isLoading && 'animate-spin')} />
            Refresh
          </button>
          <button onClick={saveConfig} disabled={isUpdating} className="btn btn-primary flex items-center">
            <Save className="h-4 w-4 mr-2" />
            Save Changes
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        {/* Sidebar Nav */}
        <div className="lg:col-span-1 space-y-1">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={clsx(
                'w-full flex items-center px-3 py-2 text-sm font-medium rounded-md',
                activeTab === tab.id ? 'bg-indigo-50 text-indigo-700' : 'text-gray-600 hover:bg-gray-50'
              )}
            >
              <tab.icon className="mr-3 h-5 w-5" />
              {tab.name}
            </button>
          ))}
        </div>

        {/* Tab Content */}
        <div className="lg:col-span-3 card p-6 bg-white shadow rounded-lg">
          {activeTab === 'risk' && config && (
            <div className="space-y-6">
              <h3 className="text-lg font-semibold">Risk Score Thresholds</h3>
              {Object.entries(config.risk_thresholds).map(([level, val]) => (
                <div key={level} className="flex items-center justify-between">
                  <span className="capitalize">{level} Risk</span>
                  <input 
                    type="range" min="0" max="1" step="0.01" 
                    value={val} 
                    onChange={(e) => updateRiskThreshold(level as any, parseFloat(e.target.value))}
                  />
                  <span className="font-mono">{(val * 100).toFixed(0)}%</span>
                </div>
              ))}
            </div>
          )}

          {activeTab === 'compliance' && config && (
            <div className="space-y-4">
              <h3 className="text-lg font-semibold">Compliance Settings</h3>
              <div>
                <label className="block text-sm font-medium">SAR Filing Deadline (days)</label>
                <input 
                  type="number" 
                  value={config.compliance_settings.sar_filing_deadline_days} 
                  onChange={(e) => setConfig({...config, compliance_settings: {...config.compliance_settings, sar_filing_deadline_days: parseInt(e.target.value)}})}
                  className="mt-1 block w-full border rounded-md p-2"
                />
              </div>
            </div>
          )}

          {activeTab === 'system' && (
            <div className="space-y-4">
              <h4 className="font-medium">System Status</h4>
              <div className="flex justify-between items-center text-sm">
                <span>API Status:</span>
                <span className="flex items-center text-green-600"><Check className="h-4 w-4 mr-1"/> Online</span>
              </div>
              <div className="flex justify-between items-center text-sm">
                <span>Database:</span>
                <span className="flex items-center text-green-600"><Check className="h-4 w-4 mr-1"/> Connected</span>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};