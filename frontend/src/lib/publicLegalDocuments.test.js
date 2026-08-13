const mocks = vi.hoisted(() => ({ get: vi.fn() }));

vi.mock("@/lib/api", () => ({
  default: { get: mocks.get },
}));

import {
  clearPublicLegalDocumentCache, loadPublicLegalDocument,
} from "./publicLegalDocuments";

beforeEach(() => {
  clearPublicLegalDocumentCache();
});

test("shares one current legal request across policy pages", async () => {
  mocks.get.mockResolvedValue({ data: { documents: {
    terms: { id: "terms", content_markdown: "# Terms\n\nCurrent terms" },
    privacy: { id: "privacy", content_markdown: "# Privacy\n\nCurrent privacy" },
  } } });

  const [terms, privacy] = await Promise.all([
    loadPublicLegalDocument("terms"),
    loadPublicLegalDocument("privacy"),
  ]);

  expect(terms.id).toBe("terms");
  expect(privacy.id).toBe("privacy");
  expect(mocks.get).toHaveBeenCalledTimes(1);
});

test("clears a failed request so a legal document can be retried", async () => {
  mocks.get
    .mockRejectedValueOnce(new Error("Temporary failure"))
    .mockResolvedValueOnce({ data: { documents: {
      terms: { id: "terms", content_markdown: "# Terms\n\nCurrent terms" },
    } } });

  await expect(loadPublicLegalDocument("terms")).rejects.toThrow("Temporary failure");
  await expect(loadPublicLegalDocument("terms")).resolves.toMatchObject({ id: "terms" });
  expect(mocks.get).toHaveBeenCalledTimes(2);
});
