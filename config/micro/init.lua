local shell = import("micro/shell")
local go_os = import("os")

-- Register rumdl with the built-in linter plugin.
function postinit()
    -- The linter plugin exposes itself as a global; import("linter") hands back
    -- a table that panics on access in micro 2.x.
    if type(linter) == "table" and type(linter.makeLinter) == "function" then
        linter.makeLinter("rumdl", "markdown", "rumdl", {"check", "%f"}, "%f:%l:%c: %m")
    end
end

function toggleWrap(bp)
    local buf = bp.Buf
    if buf.Settings["softwrap"] then
        buf:SetOption("softwrap", "false")
    else
        buf:SetOption("softwrap", "true")
    end
end

local function resolveLeaf()
    local local_leaf = go_os.Getenv("HOME") .. "/.local/bin/leaf"
    local _, err = go_os.Stat(local_leaf)
    if err == nil then
        return local_leaf
    end
    return "leaf"
end

-- Alt-m: Open leaf in a bottom split pane (up-and-down layout) with live watch mode
function previewMarkdown(bp)
    local file = bp.Buf.AbsPath
    if file == "" then
        return
    end
    local leaf = resolveLeaf()
    if go_os.Getenv("ZELLIJ") ~= "" then
        shell.ExecCommand("zellij", "run", "-d", "down", "-c", "--", leaf, "--watch", file)
    else
        shell.RunInteractiveShell(string.format("%q --watch %q", leaf, file), false, false)
    end
end

-- Alt-M (Alt+Shift+m): Open leaf in a floating pane (or inline if outside Zellij)
function previewMarkdownFloating(bp)
    local file = bp.Buf.AbsPath
    if file == "" then
        return
    end
    local leaf = resolveLeaf()
    if go_os.Getenv("ZELLIJ") ~= "" then
        shell.ExecCommand("zellij", "run", "-f", "-c", "--", leaf, "--watch", file)
    else
        previewMarkdown(bp)
    end
end
