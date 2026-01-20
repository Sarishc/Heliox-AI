interface DateRangePickerProps {
  startDate: string;
  endDate: string;
  onStartDateChange: (date: string) => void;
  onEndDateChange: (date: string) => void;
}

export default function DateRangePicker({
  startDate,
  endDate,
  onStartDateChange,
  onEndDateChange,
}: DateRangePickerProps) {
  return (
    <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h3 className="text-sm font-medium text-gray-700 mb-2">
            Date Range
          </h3>
          <p className="text-xs text-gray-500">
            Select the period for analytics
          </p>
        </div>

        <div className="flex flex-col sm:flex-row gap-3">
          <div className="flex items-center gap-2">
            <label
              htmlFor="start-date"
              className="text-sm font-medium text-gray-700 whitespace-nowrap"
            >
              From:
            </label>
            <input
              type="date"
              id="start-date"
              value={startDate}
              onChange={(e) => onStartDateChange(e.target.value)}
              className="px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
          </div>

          <div className="flex items-center gap-2">
            <label
              htmlFor="end-date"
              className="text-sm font-medium text-gray-700 whitespace-nowrap"
            >
              To:
            </label>
            <input
              type="date"
              id="end-date"
              value={endDate}
              onChange={(e) => onEndDateChange(e.target.value)}
              className="px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
          </div>
        </div>
      </div>
    </div>
  );
}

