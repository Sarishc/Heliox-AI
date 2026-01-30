"use client";

/**
 * Data Table Component
 * Enterprise table with sorting, filtering, pagination
 */

import { useState, useMemo } from "react";
import { ChevronDown, ChevronUp, Search, ChevronLeft, ChevronRight } from "lucide-react";

export interface Column<T> {
  key: string;
  label: string;
  sortable?: boolean;
  render?: (item: T) => React.ReactNode;
  width?: string;
}

interface DataTableProps<T> {
  data: T[];
  columns: Column<T>[];
  searchable?: boolean;
  searchPlaceholder?: string;
  pageSize?: number;
  emptyMessage?: string;
}

export function DataTable<T extends Record<string, any>>({
  data,
  columns,
  searchable = true,
  searchPlaceholder = "Search...",
  pageSize = 10,
  emptyMessage = "No data available",
}: DataTableProps<T>) {
  const [search, setSearch] = useState("");
  const [sortKey, setSortKey] = useState<string | null>(null);
  const [sortDirection, setSortDirection] = useState<"asc" | "desc">("asc");
  const [currentPage, setCurrentPage] = useState(1);

  // Filter data based on search
  const filteredData = useMemo(() => {
    if (!search.trim()) return data;

    const searchLower = search.toLowerCase();
    return data.filter((item) =>
      Object.values(item).some((value) =>
        String(value).toLowerCase().includes(searchLower)
      )
    );
  }, [data, search]);

  // Sort data
  const sortedData = useMemo(() => {
    if (!sortKey) return filteredData;

    return [...filteredData].sort((a, b) => {
      const aValue = a[sortKey];
      const bValue = b[sortKey];

      // Handle null/undefined
      if (aValue == null) return 1;
      if (bValue == null) return -1;

      // Compare
      let comparison = 0;
      if (typeof aValue === "number" && typeof bValue === "number") {
        comparison = aValue - bValue;
      } else {
        comparison = String(aValue).localeCompare(String(bValue));
      }

      return sortDirection === "asc" ? comparison : -comparison;
    });
  }, [filteredData, sortKey, sortDirection]);

  // Paginate data
  const totalPages = Math.ceil(sortedData.length / pageSize);
  const paginatedData = useMemo(() => {
    const start = (currentPage - 1) * pageSize;
    const end = start + pageSize;
    return sortedData.slice(start, end);
  }, [sortedData, currentPage, pageSize]);

  // Handle sort
  const handleSort = (key: string) => {
    if (sortKey === key) {
      setSortDirection((prev) => (prev === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDirection("asc");
    }
  };

  // Reset to page 1 when search changes
  useMemo(() => {
    setCurrentPage(1);
  }, [search]);

  return (
    <div className="space-y-4">
      {/* Search Bar */}
      {searchable && (
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <input
            type="text"
            placeholder={searchPlaceholder}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="
              w-full pl-10 pr-4 py-2 rounded-lg
              bg-muted border border-transparent
              text-sm text-foreground placeholder:text-muted-foreground
              focus:outline-none focus:ring-2 focus:ring-brand-500
              transition-all
            "
          />
        </div>
      )}

      {/* Table */}
      <div className="border border-border rounded-xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-muted border-b border-border">
              <tr>
                {columns.map((column) => (
                  <th
                    key={column.key}
                    onClick={() =>
                      column.sortable !== false && handleSort(column.key)
                    }
                    className={`
                      px-4 py-3 text-left text-xs font-semibold text-foreground uppercase tracking-wider
                      ${
                        column.sortable !== false
                          ? "cursor-pointer hover:bg-muted/80 select-none"
                          : ""
                      }
                      ${column.width || ""}
                    `}
                  >
                    <div className="flex items-center gap-2">
                      <span>{column.label}</span>
                      {column.sortable !== false && sortKey === column.key && (
                        <span className="text-brand-600">
                          {sortDirection === "asc" ? (
                            <ChevronUp className="w-4 h-4" />
                          ) : (
                            <ChevronDown className="w-4 h-4" />
                          )}
                        </span>
                      )}
                    </div>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {paginatedData.length === 0 ? (
                <tr>
                  <td
                    colSpan={columns.length}
                    className="px-4 py-12 text-center text-muted-foreground"
                  >
                    {emptyMessage}
                  </td>
                </tr>
              ) : (
                paginatedData.map((item, index) => (
                  <tr
                    key={index}
                    className="hover:bg-muted/50 transition-colors"
                  >
                    {columns.map((column) => (
                      <td key={column.key} className="px-4 py-3 text-sm text-foreground">
                        {column.render
                          ? column.render(item)
                          : String(item[column.key] ?? "-")}
                      </td>
                    ))}
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between">
          <div className="text-sm text-muted-foreground">
            Showing {(currentPage - 1) * pageSize + 1} to{" "}
            {Math.min(currentPage * pageSize, sortedData.length)} of{" "}
            {sortedData.length} results
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => setCurrentPage((prev) => Math.max(1, prev - 1))}
              disabled={currentPage === 1}
              className="
                p-2 rounded-lg border border-border
                hover:bg-muted disabled:opacity-50 disabled:cursor-not-allowed
                transition-colors
              "
            >
              <ChevronLeft className="w-4 h-4" />
            </button>

            <div className="flex items-center gap-1">
              {Array.from({ length: totalPages }, (_, i) => i + 1).map((page) => {
                // Show first, last, and pages around current
                if (
                  page === 1 ||
                  page === totalPages ||
                  (page >= currentPage - 1 && page <= currentPage + 1)
                ) {
                  return (
                    <button
                      key={page}
                      onClick={() => setCurrentPage(page)}
                      className={`
                        px-3 py-1.5 rounded-lg text-sm font-medium
                        transition-colors
                        ${
                          page === currentPage
                            ? "bg-brand-600 text-white"
                            : "hover:bg-muted text-foreground"
                        }
                      `}
                    >
                      {page}
                    </button>
                  );
                } else if (
                  page === currentPage - 2 ||
                  page === currentPage + 2
                ) {
                  return <span key={page} className="px-2 text-muted-foreground">...</span>;
                }
                return null;
              })}
            </div>

            <button
              onClick={() =>
                setCurrentPage((prev) => Math.min(totalPages, prev + 1))
              }
              disabled={currentPage === totalPages}
              className="
                p-2 rounded-lg border border-border
                hover:bg-muted disabled:opacity-50 disabled:cursor-not-allowed
                transition-colors
              "
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
