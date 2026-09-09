---
name: seo-audit
description: >
  Read-only technical SEO audit of a live site, plus its internal link graph. Use when the user
  asks to "audit my site", "run a technical SEO audit", "check my site's SEO health", "why isn't
  my site ranking", "find broken links", "check my robots.txt or sitemap", "are my pages
  indexable", "check Core Web Vitals", "find orphan pages", or wants a health check before or
  after a migration. Two depths: a basic pass that needs only the site, and a full pass that
  crawls the sitemap and checks speed, duplication and hreflang.
---

# Auditing a live site

```
seo audit basic <domain>              ten minutes, nothing but the site itself
seo audit full <domain> --out audits/ crawls the sitemap, speed, duplication, hreflang
seo links scan                        dead internal links and orphan pages
seo links pending <slug>              run before publishing a page
```

## Which depth

**basic** covers what breaks most often and costs nothing to check: https and redirects,
security headers, robots.txt, the XML sitemap, homepage title, meta description, canonical, H1,
image alt text, structured data, broken links, redirect chains and URL structure. Weekly, or
before you make a decision about the site.

**full** adds per-page crawling across the sitemap, Core Web Vitals from the free PageSpeed API,
duplicate content across pages, and hreflang. Quarterly, after a migration, or when traffic
moved and nobody knows why.

## The rule

**It reports. It never edits a live page.** A finding is a decision for a person, and an audit
that quietly fixed things is an audit you cannot trust. Every finding names the script behind
it so it can be reproduced by hand before anyone acts on it.

## Reading the output

Findings are grouped by area (Security, Crawlability, Indexability, On-page, Architecture,
Speed, International, Duplication) and sorted worst first.

- **FAIL** is broken and costing you something now.
- **warn** is worth fixing and is not on fire.
- **note** is context, often a legitimate choice rather than a problem.

**A clean report on a site you have not verified is a warning sign, not a result.** If the run
says nothing was checked, treat it as a failure. That is why the audit refuses to report success
having examined zero pages.

## The link graph

`seo links scan` is worth running on its own, independent of any writing. It reports dead
internal links, pages nothing links to, and links waiting on pages that have not shipped.

Two false positives it already handles, so do not be surprised: a dynamic route covers every
page beneath it, and a link to a PDF or an image is an asset link, not a page.

## After the audit

Findings become tasks for a person, or fixes proposed in the next session. Do not batch-fix
live pages from an audit run. If a fix does get made, it goes through the same gates as
anything else.
