function toggleWrap(bp)
    local buf = bp.Buf
    if buf.Settings["softwrap"] then
        buf:SetOption("softwrap", "false")
    else
        buf:SetOption("softwrap", "true")
    end
end
