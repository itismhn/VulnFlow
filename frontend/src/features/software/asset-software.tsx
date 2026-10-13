import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { Search } from "lucide-react";
import { useState } from "react";
import { Card, CardHeader, Input, Pagination, Select } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { useDebounced } from "@/lib/hooks";
import type { Page, SoftwareInstance } from "@/lib/types";
import { CATEGORY_LABELS, InstancesTable } from "./software-page";

const PAGE_SIZE = 25;

/** Software and versions on one asset, shown on the asset page. */
export function AssetSoftware({ assetId }: { assetId: number }) {
  const [q, setQ] = useState("");
  const [category, setCategory] = useState("");
  const [page, setPage] = useState(1);
  const dq = useDebounced(q);
  const { data, isFetching } = useQuery({
    queryKey: ["software", "instances", { asset_id: assetId }, dq, category, page],
    queryFn: () =>
      api.get<Page<SoftwareInstance>>("/software/instances", {
        asset_id: assetId,
        q: dq,
        category,
        page,
        page_size: PAGE_SIZE,
      }),
    placeholderData: keepPreviousData,
  });

  return (
    <Card className="mt-4 overflow-hidden">
      <CardHeader
        title="Software"
        description="OS, applications, packages, and services detected on this host, with versions"
        actions={
          <>
            <div className="relative w-52">
              <Search className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-ink-3" />
              <Input
                value={q}
                onChange={(e) => {
                  setQ(e.target.value);
                  setPage(1);
                }}
                placeholder="Filter software"
                className="h-8 pl-7 text-xs"
                aria-label="Filter software"
              />
            </div>
            <Select
              value={category}
              onChange={(e) => {
                setCategory(e.target.value);
                setPage(1);
              }}
              className="h-8 w-40 text-xs"
              aria-label="Category"
            >
              <option value="">All categories</option>
              {Object.entries(CATEGORY_LABELS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </Select>
            <Link to="/software" className="text-xs text-ink-3 hover:text-brand">
              Inventory →
            </Link>
          </>
        }
      />
      <InstancesTable data={data} fetching={isFetching} showHost={false} />
      {data && data.total > PAGE_SIZE && (
        <Pagination page={page} pageSize={PAGE_SIZE} total={data.total} onChange={setPage} />
      )}
    </Card>
  );
}
