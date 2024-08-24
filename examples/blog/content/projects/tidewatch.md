---
title: tidewatch
description: Watches a directory of CSV drops and tells you which ones are lying about their encoding.
weight: 20
tags: [python, csv]
---

At work we receive a few hundred CSV files a day from partners. All of them
say they are UTF-8. Roughly one in forty is Windows-1252 with a UTF-8 byte
order mark stuck on the front, and one memorable file was both, alternating
by row.

`tidewatch` sits on the drop directory, sniffs each new file, and writes a
one-line verdict before the file reaches the pipeline:

```text
2024-09-03T06:14:02  OK      manifest_0903.csv        utf-8      18,204 rows
2024-09-03T06:14:09  WARN    rates_north_0903.csv     cp1252     declared utf-8
2024-09-03T06:15:41  REJECT  manifest_0903_fixed.csv  mixed      rows 4411-4980
```

It does not fix anything. It took me a while to accept that the useful
tool was the one that only reports, loudly and early, and leaves the fixing
to a person who can phone the partner.

Standard library only, about 600 lines. It predates inkstone and is where
I first noticed I enjoy not having a `requirements.txt`.
