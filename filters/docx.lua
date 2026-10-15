-- Word-output tweaks (the LaTeX template handles these itself):
--  * author entries written as {name, note} become a name with a footnote
--  * a title-note becomes a footnote on the title
--  * headings get law review numbering (I., A., 1., a.) unless {.unnumbered}

local function roman(n)
  local vals = {{1000,'M'},{900,'CM'},{500,'D'},{400,'CD'},{100,'C'},{90,'XC'},
                {50,'L'},{40,'XL'},{10,'X'},{9,'IX'},{5,'V'},{4,'IV'},{1,'I'}}
  local s = ''
  for _, v in ipairs(vals) do while n >= v[1] do s = s .. v[2]; n = n - v[1] end end
  return s
end
local formats = {
  roman = roman,
  alpha = function(n) return string.char(64 + n) end,
  decimal = function(n) return tostring(n) end,
  ['alpha-lower'] = function(n) return string.char(96 + n) end,
}
-- Which numbering each heading level gets; templates override this with
-- `heading-levels: [none, roman, alpha, decimal]` in their docx.yaml.
local levels = { 'roman', 'alpha', 'decimal', 'alpha-lower' }

local function note_from(meta_value)
  return pandoc.Note({ pandoc.Para(pandoc.utils.type(meta_value) == 'Inlines'
                                   and meta_value or pandoc.Inlines(pandoc.utils.stringify(meta_value))) })
end

local function fix_meta(meta)
  if meta.author then
    local authors = pandoc.utils.type(meta.author) == 'List' and meta.author or { meta.author }
    local out = pandoc.List{}
    for _, a in ipairs(authors) do
      if pandoc.utils.type(a) == 'table' and a.name then
        local inl = pandoc.Inlines(a.name)
        if a.note then inl:insert(note_from(a.note)) end
        out:insert(pandoc.MetaInlines(inl))
      else
        out:insert(a)
      end
    end
    meta.author = out
  end
  if meta.title and meta['title-note'] then
    local t = pandoc.Inlines(meta.title)
    t:insert(note_from(meta['title-note']))
    meta.title = pandoc.MetaInlines(t)
  end
  return meta
end

local counters = {0, 0, 0, 0}
local function number_header(h)
  if h.classes:includes('unnumbered') or h.level > 4 then return nil end
  local fmt = formats[levels[h.level] or 'none']
  -- counters advance even for levels that show no number, so deeper levels restart correctly
  counters[h.level] = counters[h.level] + 1
  for i = h.level + 1, #counters do counters[i] = 0 end
  if not fmt then return nil end
  h.content:insert(1, pandoc.Space())
  h.content:insert(1, pandoc.Str(fmt(counters[h.level]) .. '.'))
  return h
end

-- One Pandoc() function so the heading settings in the metadata are read before
-- any heading is numbered (Pandoc would otherwise visit headings first).
function Pandoc(doc)
  if doc.meta['heading-levels'] then
    levels = {}
    for i, v in ipairs(doc.meta['heading-levels']) do levels[i] = pandoc.utils.stringify(v) end
  end
  doc.meta = fix_meta(doc.meta)
  doc = doc:walk { Header = number_header }
  return doc
end
