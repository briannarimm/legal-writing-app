-- Table of authorities support. A cite inserted from the citation library in a brief is
-- written in the Markdown as  [*Smith v. Jones*, 123 F.3d 456]{.auth tag="smith-v-jones"}.
-- In the PDF, each such span records the page it lands on (see \toamark in
-- templates/_brief/document.latex); scripts/make_toa.py turns those into the table.
-- Everywhere else the span is simply unwrapped.

local function category(tag)
  local data = os.getenv('LT_DATA') or '.'   -- the folder holding documents/ and library/
  local f = io.open(data .. '/library/citations/' .. tag .. '.md', 'r')
  if not f then return 'other' end
  -- "toa" is the table group written by the app (case, statute, constitution, rule, regulation, other);
  -- older files only have "type"
  local kind, toa = 'other', nil
  for line in f:lines() do
    local g = line:match('^toa:%s*"(.-)"')
    if g then toa = g; break end
    local t = line:match('^type:%s*"(.-)"')
    if t then kind = t end
    if line:match('^%-%-%-%s*$') and kind ~= 'other' then break end
  end
  if toa then kind = toa end
  f:close()
  return kind
end

local function unwrap(s)
  if s.classes:includes('auth') then return s.content end
end

local function mark(s)
  if not s.classes:includes('auth') then return nil end
  local tag = s.attributes['tag']
  if FORMAT:match('latex') and tag and tag:match('^[%w%-]+$') then
    local out = pandoc.Inlines{ pandoc.RawInline('latex', '\\toamark{' .. category(tag) .. '}{' .. tag .. '}') }
    out:extend(s.content)
    return out
  end
  return s.content
end

-- One pass over the whole document, so headings can be handled first: a mark written into a
-- heading would travel into the table of contents and break LaTeX ("extra }" in the section
-- title code), and a heading isn't a citation anyway, so marks inside headings are dropped.
function Pandoc(doc)
  doc = doc:walk { Header = function(h) h.content = h.content:walk { Span = unwrap }; return h end }
  return doc:walk { Span = mark }
end
