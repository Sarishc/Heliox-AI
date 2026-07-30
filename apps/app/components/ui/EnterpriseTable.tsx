"use client";

/**
 * Enterprise Data Table - Dense, Professional, Sortable
 * Inspired by Stripe, Datadog, Linear table designs
 */

import { useState, useMemo, ReactNode } from "react";
import {
  ChevronUp,
  ChevronDown,
  Search,
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
  Filter,
} from "lucide-react";

export interface EnterpriseColumn<T> {
  key: string;
  label: string;
  sortable?: boolean;
  width?: string;
  align?: "left" | "center" | "right";
  render?: (item: T) => ReactNode;
  className?: string;
}

interface EnterpriseTableProps<T extends Record<string, any>> {
  data: T[];
  columns: EnterpriseColumn<T>[];
  searchable?: boolean;
  searchPlaceholder?: string;
  pageSize?: number;
  emptyMessage?: string;
  dense?: boolean;
  stickyHeader?: boolean;
  className?: string;
  tags?: string[];
}

export function EnterpriseTable<T extends Record<string, any>>({
  data,
  columns,
  searchable = true,
  searchPlaceholder = "Search...",
  pageSize = 10,
  emptyMessage = "No data available",
  dense = false,
  stickyHeader = true,
  className = "",
  tags = ["env:all", "status:all"],
}: EnterpriseTableProps<T>) {
  const [search, setSearch] = useState("");
  const [sortKey, setSortKey] = useState<string | null>(null);
  const [sortDirection, setSortDirection] = useState<"asc" | "desc">("asc");
  const [currentPage, setCurrentPage] = useState(1);

  // Filter data based on search
  const filteredData = useMemo(() => {
    if (!search) return data;

    return data.filter((item) =>
      Object.values(item).some((value) =>
        String(value).toLowerCase().includes(search.toLowerCase())
      )
    );
  }, [data, search]);

  // Sort data
  const sortedData = useMemo(() => {
    if (!sortKey) return filteredData;

    return [...filteredData].sort((a, b) => {
      const aVal = a[sortKey];
      const bVal = b[sortKey];

      if (aVal === bVal) return 0;

      const comparison =
        typeof aVal === "number" && typeof bVal === "number"
          ? aVal - bVal
          : String(aVal).localeCompare(String(bVal));

      return sortDirection === "asc" ? comparison : -comparison;
    });
  }, [filteredData, sortKey, sortDirection]);

  // Paginate data
  const totalPages = Math.ceil(sortedData.length / pageSize);
  const paginatedData = useMemo(() => {
    const start = (currentPage - 1) * pageSize;
    return sortedData.slice(start, start + pageSize);
  }, [sortedData, currentPage, pageSize]);

  // Handle sort
  const handleSort = (key: string) => {
    if (sortKey === key) {
      setSortDirection(sortDirection === "asc" ? "desc" : "asc");
    } else {
      setSortKey(key);
      setSortDirection("asc");
    }
  };

  // Reset to page 1 when search changes
  useMemo(() => {
    setCurrentPage(1);
  }, [search]);

  const paddingClass = dense ? "py-1.5 px-2.5" : "py-2 px-3";

  return (
    <div className={`space-y-3 ${className}`}>
      <div className="flex flex-wrap items-center gap-1.5">
        <Filter className="h-3 w-3 text-muted-foreground" aria-hidden="true" />
        {tags.map((tag) => (
          <span
            key={tag}
            className="rounded-sm border border-border bg-muted px-1.5 py-0.5 font-mono-tabular text-[10px] text-muted-foreground"
          >
            {tag}
          </span>
        ))}
      </div>
      {/* Search Bar */}
      {searchable && (
        <div className="flex items-center justify-between gap-4">
          <div className="relative flex-1 max-w-sm">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-heliox-text-muted" />
            <input
              type="text"
              placeholder={searchPlaceholder}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="
                w-full pl-10 pr-4 py-2 
                bg-heliox-bg border border-heliox-border rounded-lg
                text-sm text-heliox-text placeholder:text-heliox-text-muted
                focus:outline-none focus:ring-2 focus:ring-heliox-primary focus:border-transparent
                transition-all
              "
            />
          </div>
          <div className="text-enterprise-small text-heliox-text-secondary">
            {filteredData.length} {filteredData.length === 1 ? "row" : "rows"}
          </div>
        </div>
      )}

      {/* Table */}
      <div className="card-enterprise overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead
              className={`
                bg-heliox-bg border-b border-heliox-border
                ${stickyHeader ? "sticky top-0 z-10" : ""}
              `}
            >
              <tr>
                {columns.map((column) => (
                  <th
                    key={column.key}
                    onClick={() =>
                      column.sortable !== false && handleSort(column.key)
                    }
                    style={{ width: column.width }}
                    className={`
                      ${paddingClass}
                      text-left text-enterprise-xs font-semibold
                      text-heliox-text-secondary uppercase tracking-wider
                      ${column.sortable !== false ? "cursor-pointer select-none hover:bg-heliox-bg-secondary" : ""}
                      ${column.align === "center" ? "text-center" : column.align === "right" ? "text-right" : ""}
                      ${column.className || ""}
                      transition-colors
                    `}
                  >
                    <div
                      className={`
                        flex items-center gap-2
                        ${column.align === "center" ? "justify-center" : column.align === "right" ? "justify-end" : ""}
                      `}
                    >
                      <span>{column.label}</span>
                      {column.sortable !== false && sortKey === column.key && (
                        <span className="text-heliox-primary">
                          {sortDirection === "asc" ? (
                            <ChevronUp className="w-3 h-3" />
                          ) : (
                            <ChevronDown className="w-3 h-3" />
                          )}
                        </span>
                      )}
                    </div>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-heliox-border-muted">
              {paginatedData.length === 0 ? (
                <tr>
                  <td
                    colSpan={columns.length}
                    className="py-12 text-center text-heliox-text-muted"
                  >
                    {emptyMessage}
                  </td>
                </tr>
              ) : (
                paginatedData.map((item, index) => (
                  <tr
                    key={index}
                    className="hover:bg-heliox-card-hover transition-colors"
                  >
                    {columns.map((column) => (
                      <td
                        key={column.key}
                        className={`
                          ${paddingClass}
                          text-enterprise-small text-heliox-text
                          ${column.align === "center" ? "text-center" : column.align === "right" ? "text-right" : ""}
                          ${column.className || ""}
                        `}
                      >
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

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between px-4 py-3 border-t border-heliox-border bg-heliox-bg">
            <div className="text-enterprise-small text-heliox-text-secondary">
              Page {currentPage} of {totalPages}
            </div>
            <div className="flex items-center gap-1">
              <button
                onClick={() => setCurrentPage(1)}
                disabled={currentPage === 1}
                className="p-1.5 rounded hover:bg-heliox-card-hover disabled:opacity-40 disabled:cursor-not-allowed"
              >
                <ChevronsLeft className="w-4 h-4" />
              </button>
              <button
                onClick={() => setCurrentPage(currentPage - 1)}
                disabled={currentPage === 1}
                className="p-1.5 rounded hover:bg-heliox-card-hover disabled:opacity-40 disabled:cursor-not-allowed"
              >
                <ChevronLeft className="w-4 h-4" />
              </button>
              <button
                onClick={() => setCurrentPage(currentPage + 1)}
                disabled={currentPage === totalPages}
                className="p-1.5 rounded hover:bg-heliox-card-hover disabled:opacity-40 disabled:cursor-not-allowed"
              >
                <ChevronRight className="w-4 h-4" />
              </button>
              <button
                onClick={() => setCurrentPage(totalPages)}
                disabled={currentPage === totalPages}
                className="p-1.5 rounded hover:bg-heliox-card-hover disabled:opacity-40 disabled:cursor-not-allowed"
              >
                <ChevronsRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
