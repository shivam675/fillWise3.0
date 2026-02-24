import { describe, it, expect } from "vitest";
import { cn, formatBytes, truncate } from "@/lib/utils";

describe("cn()", () => {
  it("merges class names", () => {
    expect(cn("foo", "bar")).toBe("foo bar");
  });

  it("deduplicates conflicting tailwind classes", () => {
    // tailwind-merge removes the first bg-* when a later one is present
    expect(cn("bg-red-500", "bg-blue-500")).toBe("bg-blue-500");
  });

  it("handles falsy values", () => {
    expect(cn("foo", false && "bar", null, undefined, "baz")).toBe("foo baz");
  });
});

describe("formatBytes()", () => {
  it("formats bytes", () => expect(formatBytes(512)).toBe("512 B"));
  it("formats KB", () => expect(formatBytes(1536)).toBe("1.5 KB"));
  it("formats MB", () => expect(formatBytes(1_572_864)).toBe("1.5 MB"));
});

describe("truncate()", () => {
  it("returns short strings unchanged", () => {
    expect(truncate("hello", 10)).toBe("hello");
  });

  it("truncates long strings", () => {
    const result = truncate("hello world", 8);
    expect(result).toBe("hello w…");
    expect(result.length).toBe(8);
  });
});
