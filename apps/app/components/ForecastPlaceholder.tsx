import React from 'react';

const ForecastPlaceholder: React.FC = () => {
  return (
    <div className="bg-white p-4 rounded-lg shadow-md h-80 flex flex-col">
      <h2 className="text-xl font-semibold text-gray-800 mb-4">
        30-Day Cost Forecast
        <span className="ml-2 text-xs bg-blue-100 text-blue-800 px-2 py-1 rounded-full">
          Coming Next Week
        </span>
      </h2>
      
      <div className="flex-grow flex items-center justify-center">
        <div className="text-center max-w-md">
          {/* Placeholder visualization */}
          <div className="mb-6 relative h-40 bg-gradient-to-b from-gray-50 to-gray-100 rounded-lg border-2 border-dashed border-gray-300 flex items-center justify-center">
            <svg
              className="w-full h-full opacity-20"
              viewBox="0 0 400 160"
              fill="none"
              xmlns="http://www.w3.org/2000/svg"
            >
              {/* Historical line */}
              <path
                d="M 10 120 L 50 100 L 90 110 L 130 90 L 170 95 L 200 80"
                stroke="#8884d8"
                strokeWidth="3"
                strokeLinecap="round"
              />
              {/* Forecast line (dashed) */}
              <path
                d="M 200 80 L 240 75 L 280 85 L 320 90 L 360 100 L 390 95"
                stroke="#82ca9d"
                strokeWidth="3"
                strokeDasharray="8 4"
                strokeLinecap="round"
              />
              {/* Confidence band */}
              <path
                d="M 200 70 L 240 65 L 280 75 L 320 80 L 360 90 L 390 85 L 390 105 L 360 110 L 320 100 L 280 95 L 240 85 L 200 90 Z"
                fill="#82ca9d"
                opacity="0.1"
              />
            </svg>
          </div>
          
          {/* Feature description */}
          <div className="space-y-3">
            <h3 className="text-lg font-medium text-gray-900">
              Predictive Cost Analytics
            </h3>
            <p className="text-sm text-gray-600 leading-relaxed">
              ML-powered forecasting will predict your GPU spending for the next 30 days
              based on historical patterns, scheduled jobs, and team activity.
            </p>
            
            {/* Feature highlights */}
            <div className="grid grid-cols-2 gap-2 mt-4 text-xs">
              <div className="bg-blue-50 p-2 rounded text-left">
                <div className="font-semibold text-blue-900">📊 Trend Analysis</div>
                <div className="text-blue-700">Detect spending anomalies</div>
              </div>
              <div className="bg-green-50 p-2 rounded text-left">
                <div className="font-semibold text-green-900">🎯 Budget Alerts</div>
                <div className="text-green-700">Prevent overruns</div>
              </div>
              <div className="bg-purple-50 p-2 rounded text-left">
                <div className="font-semibold text-purple-900">📈 Confidence Bands</div>
                <div className="text-purple-700">Best/worst case ranges</div>
              </div>
              <div className="bg-orange-50 p-2 rounded text-left">
                <div className="font-semibold text-orange-900">⚡ Real-time Updates</div>
                <div className="text-orange-700">Adapts to new data</div>
              </div>
            </div>
            
            {/* Status badge */}
            <div className="mt-4 inline-flex items-center gap-2 text-sm text-gray-600">
              <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse"></div>
              In development • Launching next week
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ForecastPlaceholder;

