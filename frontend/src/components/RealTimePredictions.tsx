import React, { useState, useEffect } from 'react';
import { Activity, Shield, ShieldAlert, Zap, Search } from 'lucide-react';
import { useApi } from '../contexts/ApiContext';
import { clsx } from 'clsx';

interface Prediction {
  id: string;
  account_id: string;
  customer: string;
  type: string;
  confidence: number;
  amount: string;
  timestamp: string;
  status: 'FLAGGED' | 'CLEAN';
  risk: number;
}

export const RealTimePredictions: React.FC = () => {
  const { api } = useApi();
  const [predictions, setPredictions] = useState<Prediction[]>([]);
  const [isScanning, setIsScanning] = useState(false);

  useEffect(() => {
    const fetchPredictions = async () => {
      try {
        setIsScanning(true);
        const response = await api.get('/live/predictions');
        setPredictions(response.data.data);
        setTimeout(() => setIsScanning(false), 1000);
      } catch (error) {
        console.error('Failed to fetch live predictions:', error);
      }
    };

    fetchPredictions();
    const interval = setInterval(fetchPredictions, 5000);
    return () => clearInterval(interval);
  }, [api]);

  return (
    <div className="h-full flex flex-col">
      <div className="pb-4 border-b border-gray-100 flex items-center justify-between">
        <div className="flex items-center space-x-2">
          <div className="live-pulse">
            <span className="bg-red-400"></span>
            <span className="bg-red-500"></span>
          </div>
          <h3 className="font-bold text-gray-800 tracking-tight">Real-Time Intelligence Feed</h3>
        </div>
        <div className="flex items-center space-x-2">
          <span className={clsx(
            "text-[10px] font-bold px-2 py-0.5 rounded border uppercase tracking-wider",
            isScanning ? "bg-primary-50 text-primary-600 border-primary-200 animate-pulse" : "bg-gray-50 text-gray-400 border-gray-200"
          )}>
            {isScanning ? 'AI Scanning...' : 'Monitoring'}
          </span>
          <Activity className={clsx("h-4 w-4 text-primary-500", isScanning && "animate-spin-slow")} />
        </div>
      </div>

      <div className="flex-1 overflow-hidden">
        <div className="divide-y divide-gray-50 max-h-[400px] overflow-y-auto custom-scrollbar">
          {predictions.map((pred) => (
            <div key={pred.id} className="feed-item p-4 flex items-start space-x-4">
              <div className={clsx(
                "mt-1 p-2 rounded-lg",
                pred.status === 'FLAGGED' ? "bg-red-50" : "bg-emerald-50"
              )}>
                {pred.status === 'FLAGGED' ? (
                  <ShieldAlert className="h-5 w-5 text-red-600" />
                ) : (
                  <Shield className="h-5 w-5 text-emerald-600" />
                )}
              </div>
              
              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between mb-0.5">
                  <span className="text-sm font-bold text-gray-900">{pred.account_id}</span>
                  <span className="text-[10px] text-gray-400 font-medium uppercase tracking-tighter">{pred.timestamp}</span>
                </div>
                
                <div className="flex items-center space-x-2 mb-1.5">
                  <span className="text-xs text-gray-500">{pred.customer}</span>
                  <span className="text-gray-300">•</span>
                  <span className="text-xs font-semibold text-gray-700">{pred.amount}</span>
                </div>

                <div className="flex items-center space-x-2">
                  <span className={clsx(
                    "text-[10px] px-1.5 py-0.5 rounded font-bold uppercase",
                    pred.status === 'FLAGGED' ? "bg-red-100 text-red-700" : "bg-emerald-100 text-emerald-700"
                  )}>
                    {pred.type}
                  </span>
                  
                  {pred.status === 'FLAGGED' && (
                    <div className="flex items-center text-[10px] font-bold text-red-500 italic">
                      <Zap className="h-3 w-3 mr-0.5 fill-current" />
                      {Math.round(pred.confidence * 100)}% Match
                    </div>
                  )}
                </div>
              </div>

              {pred.status === 'FLAGGED' && (
                <div className="flex flex-col items-center">
                  <div className="text-[10px] text-gray-400 font-bold mb-1 uppercase tracking-tighter">Risk</div>
                  <div className={clsx(
                    "w-10 h-10 rounded-full border-2 flex items-center justify-center font-bold text-xs shadow-sm",
                    pred.risk > 0.8 ? "border-red-500 text-red-600 bg-red-50" : "border-amber-500 text-amber-600 bg-amber-50"
                  )}>
                    {Math.round(pred.risk * 100)}
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
      
      <div className="p-3 bg-slate-50 border-t border-gray-100 text-center">
        <button className="text-primary-600 text-xs font-bold hover:text-primary-700 flex items-center justify-center mx-auto transition-all hover:gap-1.5">
          View Detailed Analytics <Zap className="h-3 w-3 ml-1" />
        </button>
      </div>
    </div>
  );
};
