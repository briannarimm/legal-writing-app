-- Turns redline spans ([text]{.insertion} / [text]{.deletion}, produced by
-- scripts/redline.py) into colored LaTeX. Has no effect on normal builds.
-- Footnotes are kept outside the underline/strikeout macros, which can't hold them.

local function kind(span)
  if span.classes:includes('insertion') then return 'ins' end
  if span.classes:includes('deletion') then return 'del' end
end

local function wrap(content, macro)
  local out, run = pandoc.Inlines{}, pandoc.Inlines{}
  local function flush()
    if #run > 0 then
      out:insert(pandoc.RawInline('latex', '\\' .. macro .. '{'))
      out:extend(run)
      out:insert(pandoc.RawInline('latex', '}'))
      run = pandoc.Inlines{}
    end
  end
  for _, el in ipairs(content) do
    if el.t == 'Note' then flush(); out:insert(el) else run:insert(el) end
  end
  flush()
  return out
end

function Pandoc(doc)
  if not FORMAT:match('latex') then return nil end
  -- Headings: color only (ulem breaks inside section titles and PDF bookmarks).
  doc = doc:walk {
    Header = function(h)
      h.content = h.content:walk {
        Span = function(s)
          local k = kind(s)
          if k then return wrap(s.content, k == 'ins' and 'redinsplain' or 'reddelplain') end
        end
      }
      return h
    end
  }
  return doc:walk {
    Span = function(s)
      local k = kind(s)
      if k then return wrap(s.content, k == 'ins' and 'redins' or 'reddel') end
    end
  }
end
