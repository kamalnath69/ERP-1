import { useDeferredValue, useEffect, useState } from "react";

import { RemoteCombobox } from "@/components/system";
import {
  useGetCollegeCohortsPageQuery,
  useGetCollegeCoursesPageQuery,
  useGetCollegeDepartmentsPageQuery,
  useGetCollegeOfferingsPageQuery,
  useGetCollegeProgramsPageQuery,
  useGetCollegeTermsPageQuery,
} from "@/features/college/collegeApi";
import useCursorPagination from "@/hooks/useCursorPagination";

function itemLabel(item) {
  return item.display_name || item.name || item.course_name || item.code || "Academic record";
}

function itemDescription(item) {
  if (item.display_meta) return item.display_meta;
  if (item.department_code && item.code) return `${item.department_code} / ${item.code}`;
  if (item.academic_year) return [item.academic_year, item.term_number ? `Term ${item.term_number}` : null].filter(Boolean).join(" / ");
  if (item.graduation_year) return [`Class of ${item.graduation_year}`, item.section && item.section !== "GENERAL" ? `Section ${item.section}` : null].filter(Boolean).join(" / ");
  return item.code || null;
}

export default function AcademicResourceCombobox({
  resource,
  value,
  onValueChange,
  selectedItem = null,
  filters = {},
  enabled = true,
  placeholder,
  searchPlaceholder,
  disabled = false,
}) {
  const [search, setSearch] = useState("");
  const deferredSearch = useDeferredValue(search.trim());
  const filterKey = `academic-reference:${resource}:${deferredSearch}:${JSON.stringify(filters)}`;
  const paging = useCursorPagination(filterKey);
  const args = {
    ...filters,
    q: deferredSearch || undefined,
    cursor: paging.cursor || undefined,
    limit: 25,
  };
  const options = (name) => ({ skip: !enabled || resource !== name });
  const departments = useGetCollegeDepartmentsPageQuery(args, options("departments"));
  const programs = useGetCollegeProgramsPageQuery(args, options("programs"));
  const cohorts = useGetCollegeCohortsPageQuery(args, options("cohorts"));
  const terms = useGetCollegeTermsPageQuery(args, options("terms"));
  const courses = useGetCollegeCoursesPageQuery(args, options("courses"));
  const offerings = useGetCollegeOfferingsPageQuery(args, options("offerings"));
  const query = { departments, programs, cohorts, terms, courses, offerings }[resource];
  const { accept } = paging;

  useEffect(() => {
    if (query?.data) accept(query.data);
  }, [accept, query?.data]);

  const items = paging.items;
  const resolvedSelected = items.find((item) => item.id === value)
    || (selectedItem?.id === value ? selectedItem : null);

  return <RemoteCombobox
    value={value}
    selectedItem={resolvedSelected}
    items={items}
    onValueChange={onValueChange}
    onSearchChange={setSearch}
    getLabel={itemLabel}
    getDescription={itemDescription}
    placeholder={placeholder || `Choose ${resource.replaceAll("_", " ").replace(/s$/, "")}`}
    searchPlaceholder={searchPlaceholder || `Search ${resource.replaceAll("_", " ")}`}
    emptyText={`No matching ${resource.replaceAll("_", " ")}`}
    loading={Boolean(query?.isFetching)}
    error={Boolean(query?.isError)}
    hasMore={Boolean(query?.data?.has_more)}
    onLoadMore={() => paging.loadMore(query?.data?.next_cursor)}
    onRetry={query?.refetch}
    disabled={disabled || !enabled}
  />;
}
