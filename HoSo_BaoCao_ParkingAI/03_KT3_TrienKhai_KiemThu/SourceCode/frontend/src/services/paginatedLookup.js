const DEFAULT_PAGE_SIZE = 100;

/**
 * Tải toàn bộ collection dùng contract offset pagination `skip`/`limit`.
 * Dùng cho các lookup cần đầy đủ lựa chọn thay vì âm thầm mất bản ghi sau 100.
 */
export async function requestAllOffsetPages(
  apiClient,
  url,
  pageSize = DEFAULT_PAGE_SIZE,
  baseParams = {},
) {
  const items = [];
  let skip = 0;

  while (true) {
    const response = await apiClient.get(url, {
      params: { ...baseParams, skip, limit: pageSize },
    });
    const page = response.data;
    if (!Array.isArray(page)) {
      throw new TypeError(`API lookup ${url} phải trả về một mảng`);
    }

    items.push(...page);
    if (page.length < pageSize) return items;
    skip += page.length;
  }
}
