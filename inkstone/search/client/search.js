// Browser side of inkstone search: loads the search-index.json written at
// build time and answers queries without a server.
//
// The tokenizer, stemmer and scoring are ports of the Python in
// inkstone/search and have to stay in step with it; tests/search/test_client.py
// runs both over the same input when node is around. Keep this to ES2017
// syntax, it is shipped as is and included with a plain <script> tag.
(function (root) {
  "use strict";

  const FORMAT_VERSION = 1;

  // Porter2 stemmer, line for line from stemmer.py.

  const VOWELS = "aeiouy";
  const DOUBLES = ["bb", "dd", "ff", "gg", "mm", "nn", "pp", "rr", "tt"];
  const LI_ENDINGS = "cdeghkmnrt";
  const R1_PREFIXES = ["gener", "commun", "arsen"];

  const EXCEPTIONS = {
    skis: "ski",
    skies: "sky",
    dying: "die",
    lying: "lie",
    tying: "tie",
    idly: "idl",
    gently: "gentl",
    ugly: "ugli",
    early: "earli",
    only: "onli",
    singly: "singl",
    sky: "sky",
    news: "news",
    howe: "howe",
    atlas: "atlas",
    cosmos: "cosmos",
    bias: "bias",
    andes: "andes",
  };

  const EXCEPTIONS_AFTER_1A = [
    "inning",
    "outing",
    "canning",
    "herring",
    "earring",
    "proceed",
    "exceed",
    "succeed",
  ];

  const STEP_1B = ["eedly", "ingly", "edly", "eed", "ing", "ed"];

  const STEP_2 = [
    ["ization", "ize"],
    ["ational", "ate"],
    ["fulness", "ful"],
    ["ousness", "ous"],
    ["iveness", "ive"],
    ["tional", "tion"],
    ["biliti", "ble"],
    ["lessli", "less"],
    ["entli", "ent"],
    ["ation", "ate"],
    ["alism", "al"],
    ["aliti", "al"],
    ["ousli", "ous"],
    ["iviti", "ive"],
    ["fulli", "ful"],
    ["enci", "ence"],
    ["anci", "ance"],
    ["abli", "able"],
    ["izer", "ize"],
    ["ator", "ate"],
    ["alli", "al"],
    ["bli", "ble"],
    ["ogi", "og"],
    ["li", ""],
  ];

  const STEP_3 = [
    ["ational", "ate"],
    ["tional", "tion"],
    ["alize", "al"],
    ["icate", "ic"],
    ["iciti", "ic"],
    ["ative", ""],
    ["ical", "ic"],
    ["ness", ""],
    ["ful", ""],
  ];

  const STEP_4 = [
    "ement",
    "ance",
    "ence",
    "able",
    "ible",
    "ment",
    "ant",
    "ent",
    "ism",
    "ate",
    "iti",
    "ous",
    "ive",
    "ize",
    "ion",
    "al",
    "er",
    "ic",
  ];

  function isVowel(ch) {
    return ch !== undefined && ch !== "" && VOWELS.indexOf(ch) !== -1;
  }

  function hasVowel(text) {
    for (let i = 0; i < text.length; i++) {
      if (isVowel(text[i])) return true;
    }
    return false;
  }

  function endsWithAny(word, suffixes) {
    return suffixes.some((suffix) => word.endsWith(suffix));
  }

  function markConsonantY(word) {
    if (word.indexOf("y") === -1) return word;
    const chars = word.split("");
    for (let i = 0; i < chars.length; i++) {
      if (chars[i] === "y" && (i === 0 || isVowel(chars[i - 1]))) chars[i] = "Y";
    }
    return chars.join("");
  }

  function regionAfter(word, start) {
    for (let i = start + 1; i < word.length; i++) {
      if (!isVowel(word[i]) && isVowel(word[i - 1])) return i + 1;
    }
    return word.length;
  }

  function endsInShortSyllable(word) {
    const n = word.length;
    if (n === 2) return isVowel(word[0]) && !isVowel(word[1]);
    if (n < 3) return false;
    const c = word[n - 1];
    return (
      !isVowel(word[n - 3]) && isVowel(word[n - 2]) && !isVowel(c) && "wxY".indexOf(c) === -1
    );
  }

  function step0(word) {
    const suffixes = ["'s'", "'s", "'"];
    for (let i = 0; i < suffixes.length; i++) {
      if (word.endsWith(suffixes[i])) return word.slice(0, -suffixes[i].length);
    }
    return word;
  }

  function step1a(word) {
    if (word.endsWith("sses")) return word.slice(0, -2);
    if (word.endsWith("ied") || word.endsWith("ies")) {
      return word.length > 4 ? word.slice(0, -2) : word.slice(0, -1);
    }
    if (word.endsWith("us") || word.endsWith("ss")) return word;
    if (word.endsWith("s") && hasVowel(word.slice(0, -2))) return word.slice(0, -1);
    return word;
  }

  function step1b(word, r1) {
    const suffix = STEP_1B.find((candidate) => word.endsWith(candidate));
    if (suffix === undefined) return word;
    const base = word.slice(0, -suffix.length);
    if (suffix === "eed" || suffix === "eedly") {
      return base.length >= r1 ? base + "ee" : word;
    }
    if (!hasVowel(base)) return word;
    if (endsWithAny(base, ["at", "bl", "iz"])) return base + "e";
    if (endsWithAny(base, DOUBLES)) return base.slice(0, -1);
    if (r1 >= base.length && endsInShortSyllable(base)) return base + "e";
    return base;
  }

  function step1c(word) {
    const n = word.length;
    if (n > 2 && (word[n - 1] === "y" || word[n - 1] === "Y") && !isVowel(word[n - 2])) {
      return word.slice(0, -1) + "i";
    }
    return word;
  }

  function step2(word, r1) {
    for (let i = 0; i < STEP_2.length; i++) {
      const suffix = STEP_2[i][0];
      if (!word.endsWith(suffix)) continue;
      const base = word.slice(0, -suffix.length);
      if (base.length < r1) return word;
      if (suffix === "ogi") return base.endsWith("l") ? base + "og" : word;
      if (suffix === "li") {
        return base && LI_ENDINGS.indexOf(base[base.length - 1]) !== -1 ? base : word;
      }
      return base + STEP_2[i][1];
    }
    return word;
  }

  function step3(word, r1, r2) {
    for (let i = 0; i < STEP_3.length; i++) {
      const suffix = STEP_3[i][0];
      if (!word.endsWith(suffix)) continue;
      const base = word.slice(0, -suffix.length);
      if (base.length < r1) return word;
      if (suffix === "ative" && base.length < r2) return word;
      return base + STEP_3[i][1];
    }
    return word;
  }

  function step4(word, r2) {
    for (let i = 0; i < STEP_4.length; i++) {
      const suffix = STEP_4[i];
      if (!word.endsWith(suffix)) continue;
      const base = word.slice(0, -suffix.length);
      if (base.length < r2) return word;
      if (suffix === "ion" && !base.endsWith("s") && !base.endsWith("t")) return word;
      return base;
    }
    return word;
  }

  function step5(word, r1, r2) {
    const last = word.length - 1;
    if (word.endsWith("e")) {
      if (last >= r2) return word.slice(0, -1);
      if (last >= r1 && !endsInShortSyllable(word.slice(0, -1))) return word.slice(0, -1);
    } else if (word.endsWith("ll") && last >= r2) {
      return word.slice(0, -1);
    }
    return word;
  }

  function stemUncached(input) {
    let word = input.toLowerCase().replace(/\u2019/g, "'");
    if (word.startsWith("'")) word = word.slice(1);
    if (word.length <= 2) return word;
    if (Object.prototype.hasOwnProperty.call(EXCEPTIONS, word)) return EXCEPTIONS[word];

    word = markConsonantY(word);
    const prefix = R1_PREFIXES.find((candidate) => word.startsWith(candidate));
    const r1 = prefix === undefined ? regionAfter(word, 0) : prefix.length;
    const r2 = regionAfter(word, r1);

    word = step1a(step0(word));
    if (EXCEPTIONS_AFTER_1A.indexOf(word) !== -1) return word;
    word = step1b(word, r1);
    word = step1c(word);
    word = step2(word, r1);
    word = step3(word, r1, r2);
    word = step4(word, r2);
    word = step5(word, r1, r2);
    return word.replace(/Y/g, "y");
  }

  const stemCache = new Map();

  function stem(word) {
    let result = stemCache.get(word);
    if (result === undefined) {
      result = stemUncached(word);
      if (stemCache.size > 5000) stemCache.clear();
      stemCache.set(word, result);
    }
    return result;
  }

  // Tokenizer, see tokenizer.py for the reasoning behind the rules.

  const MAX_TOKEN_LENGTH = 64;

  const FOLDS = {
    "\u00df": "ss",
    "\u00e6": "ae",
    "\u0153": "oe",
    "\u00f8": "o",
    "\u0111": "d",
    "\u00f0": "d",
    "\u00fe": "th",
    "\u0142": "l",
    "\u0127": "h",
    "\u0131": "i",
    "\u03c2": "\u03c3",
  };
  const FOLD_RE = /[\u00df\u00e6\u0153\u00f8\u0111\u00f0\u00fe\u0142\u0127\u0131\u03c2]/g;
  const COMBINING_RE = /[\u0300-\u036f\u00ad]/g;
  const ASCII_RE = /^[\x00-\x7f]*$/;

  const THOUSANDS_RE = /^[0-9]{1,3}(?:,[0-9]{3})+(?:\.[0-9]+)?$/;
  const DIGITS_RE = /^[0-9]+$/;
  const APOSTROPHE_RE = /['\u2019]/;
  const POSSESSIVE_RE = /['\u2019][sS]$/;

  function wordClass() {
    try {
      new RegExp("\\p{L}", "u");
      return { source: "[\\p{L}\\p{N}\\p{M}\\u00ad]", flags: "u" };
    } catch (err) {
      // Property escapes arrived with ES2018. Without them, take the letter
      // blocks of the BMP wholesale; a little punctuation slips in, which
      // only matters for scripts this fallback was never going to do well.
      const blocks =
        "0-9A-Za-z\\u00aa\\u00ad\\u00b5\\u00ba\\u00c0-\\u00d6\\u00d8-\\u00f6" +
        "\\u00f8-\\u1fff\\u2c00-\\u2fff\\u3040-\\ud7ff\\uf900-\\ufdff\\ufe70-\\ufefc" +
        "\\uff10-\\uffdc";
      return { source: "[" + blocks + "]", flags: "" };
    }
  }

  const WORD = wordClass();
  const WORD_RE = new RegExp(WORD.source, WORD.flags);
  const JOINER = "(?:['\\u2019]|[-\\u2010\\u2011]|_+)";
  const CHUNK_RE = new RegExp(
    "([0-9]+(?:[.,][0-9]+)+)(?!" + WORD.source + ")" +
      "|" + WORD.source + "+(?:" + JOINER + WORD.source + "+)*" +
      "(?:(?:\\+\\+|#)(?!" + WORD.source + "))?",
    WORD.flags + "g"
  );

  function fold(text) {
    text = text.toLowerCase();
    if (ASCII_RE.test(text)) return text;
    text = text.normalize("NFKD").replace(COMBINING_RE, "");
    return text.replace(FOLD_RE, (ch) => FOLDS[ch]).normalize("NFC");
  }

  function isUpper(ch) {
    return ch !== ch.toLowerCase();
  }

  function isLower(ch) {
    return ch !== ch.toUpperCase();
  }

  function camelCuts(word) {
    const cuts = [0];
    for (let i = 1; i < word.length; i++) {
      const ch = word[i];
      const prev = word[i - 1];
      if (!isUpper(ch)) continue;
      if (isLower(prev) || (prev >= "0" && prev <= "9")) {
        cuts.push(i);
      } else if (isUpper(prev) && i + 1 < word.length && isLower(word[i + 1])) {
        // HTMLParser -> HTML|Parser, but URLs and IDs stay whole
        if (word.slice(i + 1) !== "s") cuts.push(i);
      }
    }
    cuts.push(word.length);
    return cuts;
  }

  function splitChunk(chunk, offset) {
    const parts = [];
    const pieceRe = /[^-\u2010\u2011_]+/g;
    let match;
    while ((match = pieceRe.exec(chunk)) !== null) {
      let piece = match[0];
      const start = offset + match.index;
      const possessive = POSSESSIVE_RE.exec(piece);
      if (possessive && possessive.index > 0) piece = piece.slice(0, possessive.index);
      const cuts = APOSTROPHE_RE.test(piece) ? [0, piece.length] : camelCuts(piece);
      for (let i = 0; i + 1 < cuts.length; i++) {
        const text = fold(piece.slice(cuts[i], cuts[i + 1]).replace(/['\u2019]/g, ""));
        if (text) parts.push({ text: text, start: start + cuts[i], end: start + cuts[i + 1] });
      }
    }
    return parts;
  }

  function tokenize(text) {
    const tokens = [];
    let position = 0;
    let match;
    CHUNK_RE.lastIndex = 0;
    while ((match = CHUNK_RE.exec(text)) !== null) {
      let chunk = match[0];
      const start = match.index;
      const end = start + chunk.length;
      if (match[1] !== undefined) {
        if (THOUSANDS_RE.test(chunk)) chunk = chunk.replace(/,/g, "");
        if (chunk.length <= MAX_TOKEN_LENGTH) {
          tokens.push({ text: chunk, position: position, start: start, end: end, joined: false });
        }
        position += 1;
        continue;
      }
      const parts = splitChunk(chunk, start);
      if (parts.length > 1 && !parts.every((part) => DIGITS_RE.test(part.text))) {
        const whole = parts.map((part) => part.text).join("");
        if (whole.length <= MAX_TOKEN_LENGTH) {
          tokens.push({ text: whole, position: position, start: start, end: end, joined: true });
        }
      }
      for (let i = 0; i < parts.length; i++) {
        const part = parts[i];
        if (part.text.length <= MAX_TOKEN_LENGTH) {
          tokens.push({
            text: part.text,
            position: position,
            start: part.start,
            end: part.end,
            joined: false,
          });
        }
        position += 1;
      }
    }
    return tokens;
  }

  function plainWord(text) {
    return tokenize(text)
      .filter((token) => !token.joined)
      .map((token) => token.text)
      .join("");
  }

  // Query syntax, same as parse_query() in query.py.

  const TERM = "term";
  const PHRASE = "phrase";
  const PREFIX = "prefix";
  const FUZZY = "fuzzy";

  const SHOULD = "should";
  const MUST = "must";
  const MUST_NOT = "must_not";

  const FUZZY_WEIGHT = 0.5;
  const MAX_FUZZY_TERMS = 50;
  const MAX_PREFIX_TERMS = 200;
  const COMPLETIONS = [""].concat("s e d g n es ed ng on ly ss al ing ion ess".split(" "));

  function isSpace(ch) {
    return /\s/.test(ch);
  }

  function classify(word) {
    if (word.length > 1 && word.endsWith("*")) return [word.replace(/\*+$/, ""), PREFIX];
    const match = /~[0-9]?$/.exec(word);
    if (match && match.index > 0) {
      return [word.slice(0, match.index), match[0] === "~0" ? TERM : FUZZY];
    }
    return [word, TERM];
  }

  function fieldPrefix(text, i, fields) {
    const colon = text.indexOf(":", i);
    if (colon <= i || colon + 1 >= text.length) return null;
    const next = text[colon + 1];
    if (isSpace(next) || next === "/") return null;
    const name = text.slice(i, colon);
    return fields.indexOf(name) !== -1 ? name : null;
  }

  function parseQuery(text, fields) {
    text = text.replace(/[\u201c\u201d\u201e\u00ab\u00bb]/g, '"');
    const clauses = [];
    const n = text.length;
    let i = 0;
    while (i < n) {
      if (isSpace(text[i])) {
        i += 1;
        continue;
      }
      let occur = SHOULD;
      if ((text[i] === "+" || text[i] === "-") && i + 1 < n && !isSpace(text[i + 1])) {
        occur = text[i] === "+" ? MUST : MUST_NOT;
        i += 1;
      }
      const field = fieldPrefix(text, i, fields || []);
      if (field !== null) i += field.length + 1;
      let body;
      let kind;
      if (text[i] === '"') {
        let end = text.indexOf('"', i + 1);
        if (end < 0) end = n;
        body = text.slice(i + 1, end).trim();
        kind = PHRASE;
        i = end + 1;
      } else {
        let end = i;
        while (end < n && !isSpace(text[end]) && text[end] !== '"') end += 1;
        const classified = classify(text.slice(i, end));
        body = classified[0];
        kind = classified[1];
        i = end;
      }
      if (WORD_RE.test(body)) {
        clauses.push({ kind: kind, text: body, field: field, occur: occur });
      }
    }
    return clauses;
  }

  function withinOneEdit(a, b) {
    if (a.length > b.length) {
      const swap = a;
      a = b;
      b = swap;
    }
    let i = 0;
    while (i < a.length && a[i] === b[i]) i += 1;
    if (a.length !== b.length) return a.slice(i) === b.slice(i + 1);
    if (a.slice(i + 1) === b.slice(i + 1)) return true;
    return (
      a.length - i >= 2 &&
      a[i] === b[i + 1] &&
      a[i + 1] === b[i] &&
      a.slice(i + 2) === b.slice(i + 2)
    );
  }

  // Postings arrive as one flat array per term:
  // [field, ndocs, (doc delta, npos, position deltas...)..., field, ...]
  function decodePostings(flat) {
    const byField = new Map();
    let i = 0;
    while (i < flat.length) {
      const field = flat[i];
      const ndocs = flat[i + 1];
      i += 2;
      let docs = byField.get(field);
      if (docs === undefined) {
        docs = new Map();
        byField.set(field, docs);
      }
      let doc = 0;
      for (let d = 0; d < ndocs; d++) {
        doc += flat[i];
        const count = flat[i + 1];
        i += 2;
        const positions = new Array(count);
        let position = 0;
        for (let p = 0; p < count; p++) {
          position += flat[i + p];
          positions[p] = position;
        }
        i += count;
        docs.set(doc, positions);
      }
    }
    return byField;
  }

  const NO_POSTINGS = new Map();

  class Index {
    constructor(data) {
      if (!data || data.version !== FORMAT_VERSION) {
        const found = data ? data.version : undefined;
        throw new Error(
          "inkstone search: unsupported index format " + found + ", expected " + FORMAT_VERSION
        );
      }
      const config = data.config || {};
      if (config.stemmer && config.stemmer !== "english") {
        throw new Error("inkstone search: unknown stemmer " + config.stemmer);
      }
      this.stemmer = config.stemmer || null;
      this.minTokenLength = config.min_token_length || 1;
      this.k1 = config.k1 === undefined ? 1.2 : config.k1;
      this.b = config.b === undefined ? 0.75 : config.b;
      this.stopwords = new Set(data.stopwords || []);
      this.fields = data.fields;
      this.boosts = data.boosts;
      this.store = data.store || [];
      this.docs = data.docs;
      this.vocab = data.vocab;
      this.forms = data.forms || {};
      this.encoded = data.postings;
      this.decoded = new Map();
      this.terms = new Map();
      this.vocab.forEach((term, i) => this.terms.set(term, i));
      const count = this.docs.length || 1;
      this.averageLengths = this.fields.map(
        (name, f) => this.docs.reduce((sum, doc) => sum + doc[1][f], 0) / count
      );
    }

    term(word) {
      if (word.length < this.minTokenLength || this.stopwords.has(word)) return null;
      return this.stemmer ? stem(word) : word;
    }

    analyze(text) {
      const tokens = [];
      tokenize(text).forEach((token) => {
        const term = this.term(token.text);
        if (term !== null) {
          token.text = term;
          tokens.push(token);
        }
      });
      return tokens;
    }

    postings(term) {
      const i = this.terms.get(term);
      if (i === undefined) return NO_POSTINGS;
      let decoded = this.decoded.get(i);
      if (decoded === undefined) {
        decoded = decodePostings(this.encoded[i]);
        this.decoded.set(i, decoded);
      }
      return decoded;
    }

    docFrequency(term) {
      const docs = new Set();
      this.postings(term).forEach((byDoc) => byDoc.forEach((positions, doc) => docs.add(doc)));
      return docs.size;
    }

    expandPrefix(prefix, limit) {
      // A plain scan: the vocabulary was sorted by code point in Python and
      // JS compares UTF-16 units, so a binary search could go wrong on astral
      // characters. Fifty thousand startsWith calls are not worth worrying about.
      const terms = [];
      for (let i = 0; i < this.vocab.length; i++) {
        if (!this.vocab[i].startsWith(prefix)) continue;
        if (limit !== null && terms.length >= limit) break;
        terms.push(this.vocab[i]);
      }
      if (this.stemmer) {
        // the vocabulary holds stems; see expand_prefix() in index.py
        COMPLETIONS.forEach((ending) => {
          const term = stem(prefix + ending);
          if (this.terms.has(term) && terms.indexOf(term) === -1) terms.push(term);
        });
      }
      return terms;
    }

    bm25f(tfs) {
      const weighted = new Map();
      tfs.forEach((docs, f) => {
        const boost = this.boosts[f];
        const average = this.averageLengths[f] || 1;
        docs.forEach((tf, doc) => {
          const norm = 1 - this.b + (this.b * this.docs[doc][1][f]) / average;
          weighted.set(doc, (weighted.get(doc) || 0) + (boost * tf) / norm);
        });
      });
      const df = weighted.size;
      const idf = Math.log(1 + (this.docs.length - df + 0.5) / (df + 0.5));
      const scores = new Map();
      weighted.forEach((w, doc) => scores.set(doc, (idf * w) / (this.k1 + w)));
      return scores;
    }

    termMatch(fields, weights) {
      const match = { tfs: new Map(), terms: [] };
      weights.forEach((weight, term) => {
        const postings = this.postings(term);
        fields.forEach((f) => {
          const docs = postings.get(f);
          if (docs === undefined || docs.size === 0) return;
          let tfs = match.tfs.get(f);
          if (tfs === undefined) {
            tfs = new Map();
            match.tfs.set(f, tfs);
          }
          docs.forEach((positions, doc) => {
            tfs.set(doc, (tfs.get(doc) || 0) + weight * positions.length);
          });
          match.terms.push([f, term, docs]);
        });
      });
      return match;
    }

    phraseMatch(fields, tokens) {
      const terms = tokens.map((token) => token.text);
      const offsets = tokens.map((token) => token.position - tokens[0].position);
      const postings = terms.map((term) => this.postings(term));
      const match = { tfs: new Map(), terms: [] };
      fields.forEach((f) => {
        const lists = postings.map((byField) => byField.get(f));
        if (lists.some((docs) => docs === undefined || docs.size === 0)) return;
        const found = new Map();
        lists[0].forEach((starts, doc) => {
          if (!lists.every((docs) => docs.has(doc))) return;
          const rest = lists.slice(1).map((docs) => new Set(docs.get(doc)));
          let count = 0;
          starts.forEach((start) => {
            if (rest.every((seen, k) => seen.has(start + offsets[k + 1]))) count += 1;
          });
          if (count) found.set(doc, count);
        });
        if (found.size) {
          match.tfs.set(f, found);
          Array.from(new Set(terms)).forEach((term) => match.terms.push([f, term, found]));
        }
      });
      return match;
    }

    fuzzyTerms(word, term) {
      const weights = new Map([[term, 1]]);
      if (word.length < 3) return weights;
      // typos change how a word stems, so compare what was typed as well,
      // and against the display spelling of each term; see query.py
      const typed = word === term ? [word] : [word, term];
      for (let i = 0; i < this.vocab.length; i++) {
        const candidate = this.vocab[i];
        if (candidate === term) continue;
        const form = this.forms[i];
        const spellings = form === undefined ? [candidate] : [candidate, form];
        const close = typed.some((a) =>
          spellings.some((b) => Math.abs(a.length - b.length) <= 1 && withinOneEdit(a, b))
        );
        if (close) {
          weights.set(candidate, FUZZY_WEIGHT);
          if (weights.size > MAX_FUZZY_TERMS) break;
        }
      }
      return weights;
    }

    matchClause(clause) {
      let fields;
      if (clause.field === null || clause.field === undefined) {
        fields = this.fields.map((name, f) => f);
      } else if (this.fields.indexOf(clause.field) !== -1) {
        fields = [this.fields.indexOf(clause.field)];
      } else {
        return { tfs: new Map(), terms: [] };
      }

      if (clause.kind === PREFIX || clause.kind === FUZZY) {
        const word = plainWord(clause.text);
        if (!word) return null;
        if (clause.kind === PREFIX) {
          const weights = new Map();
          this.expandPrefix(word, MAX_PREFIX_TERMS).forEach((term) => weights.set(term, 1));
          return this.termMatch(fields, weights);
        }
        const term = this.term(word);
        if (term === null) return null;
        return this.termMatch(fields, this.fuzzyTerms(word, term));
      }

      const tokens = this.analyze(clause.text);
      if (!tokens.length) return null;
      const parts = tokens.filter((token) => !token.joined);
      const wholes = tokens.filter((token) => token.joined);
      if (!parts.length) return this.termMatch(fields, new Map([[wholes[0].text, 1]]));
      let match;
      if (parts.length === 1) {
        match = this.termMatch(fields, new Map([[parts[0].text, 1]]));
      } else {
        match = this.phraseMatch(fields, parts);
      }
      if (clause.kind === TERM && wholes.length === 1) {
        const whole = wholes[0];
        if (whole.start <= parts[0].start && whole.end >= parts[parts.length - 1].end) {
          const other = this.termMatch(fields, new Map([[whole.text, 1]]));
          other.tfs.forEach((docs, f) => {
            let tfs = match.tfs.get(f);
            if (tfs === undefined) {
              tfs = new Map();
              match.tfs.set(f, tfs);
            }
            docs.forEach((tf, doc) => {
              if (tf > (tfs.get(doc) || 0)) tfs.set(doc, tf);
            });
          });
          match.terms = match.terms.concat(other.terms);
        }
      }
      return match;
    }

    search(query, options) {
      const limit = options && options.limit !== undefined ? options.limit : 10;
      const clauses = typeof query === "string" ? parseQuery(query, this.fields) : query;
      const required = [];
      const optional = [];
      const excluded = new Set();
      clauses.forEach((clause) => {
        const match = this.matchClause(clause);
        if (match === null) return;
        if (clause.occur === MUST_NOT) {
          match.tfs.forEach((docs) => docs.forEach((tf, doc) => excluded.add(doc)));
        } else if (clause.occur === MUST) {
          required.push(match);
        } else {
          optional.push(match);
        }
      });

      const matched = required.concat(optional);
      const scored = matched.map((match) => this.bm25f(match.tfs));
      if (!scored.length) return [];
      const candidates = new Set();
      if (required.length) {
        scored[0].forEach((score, doc) => {
          if (scored.slice(1, required.length).every((scores) => scores.has(doc))) {
            candidates.add(doc);
          }
        });
      } else {
        scored.forEach((scores) => scores.forEach((score, doc) => candidates.add(doc)));
      }

      let ranked = [];
      candidates.forEach((doc) => {
        if (excluded.has(doc)) return;
        let total = 0;
        scored.forEach((scores) => {
          total += scores.get(doc) || 0;
        });
        ranked.push([doc, total]);
      });
      ranked.sort((x, y) => y[1] - x[1] || x[0] - y[0]);
      if (limit !== null) ranked = ranked.slice(0, Math.max(limit, 0));

      return ranked.map((entry) => {
        const doc = entry[0];
        const found = {};
        matched.forEach((match) => {
          match.terms.forEach((item) => {
            if (!item[2].has(doc)) return;
            const name = this.fields[item[0]];
            if (!found[name]) found[name] = new Set();
            found[name].add(item[1]);
          });
        });
        const matches = {};
        this.fields.forEach((name) => {
          if (found[name]) matches[name] = Array.from(found[name]).sort();
        });
        const stored = {};
        this.store.forEach((name, i) => {
          const value = this.docs[doc][2][i];
          if (value !== null && value !== undefined) stored[name] = value;
        });
        return { id: this.docs[doc][0], score: entry[1], stored: stored, matches: matches };
      });
    }

    suggest(prefix, options) {
      const limit = options && options.limit !== undefined ? options.limit : 5;
      prefix = plainWord(prefix);
      if (!prefix || limit <= 0) return [];
      const ranked = this.expandPrefix(prefix, null).map((term) => {
        return [this.terms.get(term), this.docFrequency(term)];
      });
      // vocabulary order stands in for comparing the strings, which JS would
      // do by UTF-16 unit rather than by code point
      ranked.sort((x, y) => y[1] - x[1] || x[0] - y[0]);
      const words = [];
      for (let i = 0; i < ranked.length && words.length < limit; i++) {
        const word = this.forms[ranked[i][0]] || this.vocab[ranked[i][0]];
        if (words.indexOf(word) === -1) words.push(word);
      }
      return words;
    }

    // Split text into [string, isMatch] pairs for the words that analyze to
    // one of the given index terms.
    highlight(text, terms) {
      const wanted = new Set(terms);
      const spans = [];
      this.analyze(text).forEach((token) => {
        if (!wanted.has(token.text)) return;
        const last = spans[spans.length - 1];
        if (last && token.start < last[1]) last[1] = Math.max(last[1], token.end);
        else spans.push([token.start, token.end]);
      });
      const segments = [];
      let cursor = 0;
      spans.forEach((span) => {
        if (span[0] > cursor) segments.push([text.slice(cursor, span[0]), false]);
        segments.push([text.slice(span[0], span[1]), true]);
        cursor = span[1];
      });
      if (cursor < text.length) segments.push([text.slice(cursor), false]);
      return segments;
    }
  }

  // The index most pages want: the one from load(), shared by search(),
  // suggest() and every attached search box.
  let defaultIndex = null;
  const waiting = [];

  function load(url) {
    return fetch(url, { credentials: "same-origin" })
      .then((response) => {
        if (!response.ok) {
          throw new Error("inkstone search: " + url + " answered " + response.status);
        }
        return response.json();
      })
      .then((data) => {
        defaultIndex = new Index(data);
        waiting.splice(0).forEach((callback) => callback());
        return defaultIndex;
      });
  }

  function requireIndex() {
    if (defaultIndex === null) {
      throw new Error("inkstone search: no index yet, wait for InkstoneSearch.load(url)");
    }
    return defaultIndex;
  }

  function search(query, options) {
    return requireIndex().search(query, options);
  }

  function suggest(prefix, options) {
    return requireIndex().suggest(prefix, options);
  }

  const DEFAULTS = {
    limit: 8,
    debounce: 120,
    minLength: 2,
    // treat the word being typed as a prefix, so results show up before it
    // is finished
    prefix: true,
    // fetch the index from here on first focus instead of on page load
    url: null,
    index: null,
    emptyText: "No results",
    activeClass: "is-active",
    renderItem: null,
  };

  let attachCount = 0;

  function liveQuery(text) {
    const quotes = (text.match(/"/g) || []).length;
    if (!text || quotes % 2 === 1 || !WORD_RE.test(text[text.length - 1])) return text;
    return text + "*";
  }

  function appendHighlighted(parent, index, text, terms) {
    const doc = parent.ownerDocument;
    index.highlight(text, terms).forEach((segment) => {
      if (segment[1]) {
        const mark = doc.createElement("mark");
        mark.textContent = segment[0];
        parent.appendChild(mark);
      } else {
        parent.appendChild(doc.createTextNode(segment[0]));
      }
    });
  }

  function defaultItem(hit, index, doc) {
    const terms = [];
    Object.keys(hit.matches).forEach((name) => {
      hit.matches[name].forEach((term) => terms.push(term));
    });
    const link = doc.createElement("a");
    link.href = hit.stored.url || hit.id;
    const title = doc.createElement("span");
    title.className = "inkstone-search-title";
    appendHighlighted(title, index, String(hit.stored.title || hit.id), terms);
    link.appendChild(title);
    if (hit.stored.summary) {
      const summary = doc.createElement("span");
      summary.className = "inkstone-search-summary";
      appendHighlighted(summary, index, String(hit.stored.summary), terms);
      link.appendChild(summary);
    }
    return link;
  }

  function attach(input, results, options) {
    const opts = Object.assign({}, DEFAULTS, options || {});
    const doc = input.ownerDocument;
    const itemTag = /^(UL|OL)$/i.test(results.tagName || "") ? "li" : "div";
    attachCount += 1;
    const idPrefix = "inkstone-search-" + attachCount + "-";
    let timer = null;
    let items = [];
    let active = -1;
    let requested = false;

    if (!results.id) results.id = idPrefix + "results";
    results.setAttribute("role", "listbox");
    input.setAttribute("role", "combobox");
    input.setAttribute("autocomplete", "off");
    input.setAttribute("aria-autocomplete", "list");
    input.setAttribute("aria-controls", results.id);
    input.setAttribute("aria-expanded", "false");

    function currentIndex() {
      return opts.index || defaultIndex;
    }

    function setActive(next) {
      if (items[active]) {
        items[active].classList.remove(opts.activeClass);
        items[active].setAttribute("aria-selected", "false");
      }
      active = next;
      if (items[active]) {
        items[active].classList.add(opts.activeClass);
        items[active].setAttribute("aria-selected", "true");
        input.setAttribute("aria-activedescendant", items[active].id);
        if (items[active].scrollIntoView) items[active].scrollIntoView({ block: "nearest" });
      } else {
        input.removeAttribute("aria-activedescendant");
      }
    }

    function close() {
      while (results.firstChild) results.removeChild(results.firstChild);
      items = [];
      setActive(-1);
      results.hidden = true;
      input.setAttribute("aria-expanded", "false");
    }

    function show(hits, index) {
      close();
      hits.forEach((hit, i) => {
        const item = doc.createElement(itemTag);
        item.id = idPrefix + i;
        item.className = "inkstone-search-result";
        item.setAttribute("role", "option");
        item.setAttribute("aria-selected", "false");
        const render = opts.renderItem || defaultItem;
        item.appendChild(render(hit, index, doc));
        results.appendChild(item);
        items.push(item);
      });
      if (!hits.length) {
        const empty = doc.createElement(itemTag);
        empty.className = "inkstone-search-empty";
        empty.textContent = opts.emptyText;
        results.appendChild(empty);
      }
      results.hidden = false;
      input.setAttribute("aria-expanded", "true");
    }

    function update() {
      timer = null;
      const index = currentIndex();
      const text = input.value.trim();
      if (text.length < opts.minLength) {
        close();
        return;
      }
      if (!index) {
        // typed before the index arrived; run again once it is there
        if (waiting.indexOf(update) === -1) waiting.push(update);
        return;
      }
      const query = opts.prefix ? liveQuery(input.value) : text;
      show(index.search(query, { limit: opts.limit }), index);
    }

    function schedule() {
      if (timer !== null) clearTimeout(timer);
      timer = setTimeout(update, opts.debounce);
    }

    function ensureLoaded() {
      if (requested || !opts.url || currentIndex()) return;
      requested = true;
      load(opts.url).catch((err) => {
        requested = false;
        if (typeof console !== "undefined") console.error(err);
      });
    }

    function onKeydown(event) {
      const key = event.key;
      if (key === "ArrowDown" || key === "ArrowUp") {
        if (!items.length) return;
        event.preventDefault();
        const step = key === "ArrowDown" ? 1 : -1;
        // -1 is "nothing selected": going up from there wraps to the last hit
        const from = active === -1 && step === -1 ? items.length : active;
        setActive((from + step + items.length) % items.length);
      } else if (key === "Enter") {
        if (!items[active]) return;
        const link = items[active].querySelector ? items[active].querySelector("a") : null;
        if (link) {
          event.preventDefault();
          link.click();
        }
      } else if (key === "Escape") {
        if (results.hidden) return;
        event.preventDefault();
        close();
      }
    }

    function onDocumentClick(event) {
      if (event.target === input || results.contains(event.target)) return;
      close();
    }

    function onFocus() {
      ensureLoaded();
      if (results.hidden && input.value.trim()) schedule();
    }

    function onInput() {
      ensureLoaded();
      schedule();
    }

    input.addEventListener("input", onInput);
    input.addEventListener("focus", onFocus);
    input.addEventListener("keydown", onKeydown);
    doc.addEventListener("click", onDocumentClick);
    close();

    return {
      update: update,
      close: close,
      destroy() {
        if (timer !== null) clearTimeout(timer);
        const queued = waiting.indexOf(update);
        if (queued !== -1) waiting.splice(queued, 1);
        input.removeEventListener("input", onInput);
        input.removeEventListener("focus", onFocus);
        input.removeEventListener("keydown", onKeydown);
        doc.removeEventListener("click", onDocumentClick);
        close();
      },
    };
  }

  const InkstoneSearch = {
    FORMAT_VERSION: FORMAT_VERSION,
    Index: Index,
    load: load,
    search: search,
    suggest: suggest,
    attach: attach,
    parseQuery: parseQuery,
    tokenize: tokenize,
    fold: fold,
    stem: stem,
  };

  if (typeof module === "object" && module.exports) {
    module.exports = InkstoneSearch;
  } else {
    root.InkstoneSearch = InkstoneSearch;
  }
})(typeof self !== "undefined" ? self : this);
