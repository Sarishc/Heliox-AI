# Heliox Forecasting V1

Production-ready GPU usage and cost forecasting for the Heliox platform.

## 🎯 Overview

Heliox Forecasting provides reliable, ML-powered predictions for GPU usage and costs. The system uses a two-tiered approach: a simple, robust baseline that always works, and an optional ML upgrade when sufficient data is available.

## ✅ Features

- **Two Forecasting Methods**:
  - **Moving Average + Trend** (< 30 days data): Simple, deterministic, always reliable
  - **LightGBM** (≥ 30 days data): ML-powered with lag and time features
  
- **95% Confidence Intervals**: Realistic uncertainty bands that widen over forecast horizon

- **Redis Caching**: 1-hour TTL for repeated queries, graceful fallback if unavailable

- **Flexible Filtering**: By provider (aws, gcp, azure) and GPU type (a100, h100, v100)

- **Comprehensive Testing**: 10 test cases covering all edge cases

## 🚀 API Endpoints

### 1. Forecast GPU Spending

```bash
GET /api/v1/forecast/spend
```

**Query Parameters:**
- `provider` (optional): Filter by cloud provider (e.g., "aws", "gcp")
- `gpu_type` (optional): Filter by GPU type (e.g., "a100", "h100")
- `horizon_days` (optional): Days to forecast (1-30, default: 7)

**Example:**
```bash
curl "http://localhost:8000/api/v1/forecast/spend?provider=aws&horizon_days=7"
```

**Response:**
```json
{
  "provider": "aws",
  "gpu_type": null,
  "horizon_days": 7,
  "forecast_method": "moving_average",
  "historical": [
    {"date": "2026-01-01", "value": 3435.12},
    {"date": "2026-01-02", "value": 3544.10},
    ...
  ],
  "forecast": [
    {
      "date": "2026-01-15",
      "value": 3724.76,
      "lower_bound": 2545.12,
      "upper_bound": 4904.41
    },
    ...
  ],
  "metadata": {
    "historical_data_points": 14,
    "forecast_generated_at": "2026-01-09"
  }
}
```

### 2. Forecast GPU Usage

```bash
GET /api/v1/forecast/usage
```

**Query Parameters:** Same as `/forecast/spend`

**Example:**
```bash
curl "http://localhost:8000/api/v1/forecast/usage?gpu_type=h100&horizon_days=14"
```

### 3. Health Check

```bash
GET /api/v1/forecast/health
```

**Example:**
```bash
curl "http://localhost:8000/api/v1/forecast/health"
```

**Response:**
```json
{
  "status": "ok",
  "features": {
    "database": "connected",
    "redis_caching": "available",
    "lightgbm_ml": "available",
    "forecast_methods": ["moving_average", "lightgbm"]
  },
  "limits": {
    "min_data_points": 7,
    "max_horizon_days": 30,
    "default_horizon_days": 7
  }
}
```

## 📊 Forecasting Algorithms

### Moving Average + Trend (Baseline)

Used when **< 30 days** of historical data available.

**How it works:**
1. Calculate 7-day moving average for smoothing
2. Fit linear regression on recent 14 days for trend
3. Project trend forward
4. Calculate confidence bands from historical volatility (standard deviation)

**Advantages:**
- Always works (no ML dependencies)
- Deterministic and explainable
- Fast computation
- Reliable for short-term forecasts

### LightGBM (ML Model)

Used when **≥ 30 days** of historical data available.

**Features:**
- **Lag features**: t-1, t-2, t-3, t-7, t-14
- **Time features**: Day of week
- **Early stopping**: Prevents overfitting
- **RMSE-based confidence**: Based on model's historical performance

**Advantages:**
- Captures complex patterns
- Better for long-term forecasts
- Adapts to seasonality
- Falls back to baseline if fails

## 🔧 Technical Details

### Data Requirements

- **Minimum**: 7 days for any forecast
- **ML upgrade**: 30+ days for LightGBM
- **Recommended**: 30-90 days for best accuracy

### Forecast Limits

- **Horizon**: 1-30 days
- **Default**: 7 days

### Confidence Bands

- **Level**: 95% confidence intervals
- **Calculation**: Based on historical standard deviation
- **Behavior**: Widen over forecast horizon (sqrt scaling)
- **Constraint**: Always non-negative

### Caching

- **Storage**: Redis
- **TTL**: 1 hour (3600 seconds)
- **Cache key**: Includes forecast type, provider, gpu_type, and horizon
- **Fallback**: Works without Redis (no caching)

## 🧪 Testing

Run the comprehensive test suite:

```bash
cd backend
pytest tests/test_forecasting.py -v
```

**Test Coverage:**
- Output shape validation
- Insufficient data handling
- Horizon validation (1-30 days)
- Trend detection
- Confidence band properties (widening)
- Caching behavior
- Non-negativity constraints
- Metadata validation
- Method selection logic

## 📁 File Structure

```
backend/
├── app/
│   ├── api/
│   │   └── routes/
│   │       └── forecast.py          # API endpoints
│   ├── services/
│   │   └── forecasting.py           # Core forecasting logic
│   ├── schemas/
│   │   └── forecast.py              # Pydantic schemas
│   └── core/
│       └── cache.py                 # Redis utilities
└── tests/
    └── test_forecasting.py          # Test suite
```

## 🎯 Use Cases

1. **Budget Planning**: Forecast spending for next month/quarter
2. **Capacity Planning**: Predict GPU usage to avoid shortages
3. **Cost Alerts**: Set thresholds based on forecast upper bounds
4. **Financial Reporting**: Project costs for stakeholders
5. **Resource Optimization**: Identify trends to optimize allocation

## 🔍 Example Workflows

### Monthly Budget Forecast

```bash
# Get 30-day spending forecast
curl "http://localhost:8000/api/v1/forecast/spend?horizon_days=30" | jq '.forecast | map(.value) | add'
```

### Team-Specific Capacity Planning

```bash
# Forecast AWS usage for next 14 days
curl "http://localhost:8000/api/v1/forecast/usage?provider=aws&horizon_days=14"
```

### GPU Type Analysis

```bash
# Compare H100 vs A100 spending forecasts
curl "http://localhost:8000/api/v1/forecast/spend?gpu_type=h100&horizon_days=7"
curl "http://localhost:8000/api/v1/forecast/spend?gpu_type=a100&horizon_days=7"
```

## 🚨 Error Handling

### Insufficient Data

```json
{
  "error": "Insufficient historical data. Need at least 7 days, found 3.",
  "historical": [],
  "forecast": []
}
```

**Solution**: Collect more historical data before forecasting.

### Invalid Horizon

Horizon is automatically clamped to 1-30 days.

### Database Errors

Returns 500 with detailed error message in logs.

## 🎨 Design Philosophy

**Reliable Over Fancy**

1. ✅ Simple baseline always works (no ML dependencies required)
2. ✅ ML model only when sufficient data exists
3. ✅ Clear indication of which method was used
4. ✅ Graceful degradation at every level
5. ✅ Non-negative constraints enforced
6. ✅ Realistic confidence bands (widen over time)
7. ✅ Comprehensive error messages
8. ✅ Production-ready caching

## 📈 Future Enhancements

- [ ] Multi-horizon forecasts (1-day, 7-day, 30-day in single call)
- [ ] Forecast accuracy metrics (MAPE, RMSE)
- [ ] Anomaly detection in forecasts
- [ ] Seasonal decomposition
- [ ] Prophet model support
- [ ] Forecast explanations (feature importance)
- [ ] Forecast comparison (actual vs predicted)
- [ ] Auto-tuning of forecast parameters

## 🎊 Summary

Heliox Forecasting V1 is **production-ready** and provides:

- ✅ Reliable baseline forecasting (always works)
- ✅ ML-powered forecasting (when data permits)
- ✅ 95% confidence intervals
- ✅ Redis caching for performance
- ✅ Comprehensive testing (10 test cases)
- ✅ Production-ready error handling
- ✅ Full Swagger documentation

**Ready for production deployment!** 🚀

