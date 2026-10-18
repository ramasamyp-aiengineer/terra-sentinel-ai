
        Add-Type -AssemblyName System.Speech
        $s = New-Object System.Speech.Synthesis.SpeechSynthesizer
        $s.Rate = -1
        $s.Volume = 100
        try { $s.SelectVoiceByHints([System.Speech.Synthesis.VoiceGender]::Female) } catch {}
        $s.SetOutputToWaveFile('d:\Ram\TerraSentinelAI\docs\pitch\video\_build\narration.wav')
        $s.Speak(@'
Which 250 metres should an engineer inspect today?
Satellites see the ground move. TerraSentinel ranks what matters.
Gemini tells the engineer where to go first.

After one pass on our demonstration dataset — labelled synthetic —
we have sixty-two thousand displacement observations,
cut into eighty-seven sites of two hundred and fifty metres.
Only seven are Critical or Elevated. Four need a crew today.

Everything starts in Data Hub.
Engineers upload InSAR points, time series, assets and rainfall —
or import from a link.
Every file is validated in plain language before it enters the model.
Provenance is kept for every dataset.

Zoom to Chamoli. Sixty-nine sites along the Himalayan corridor.
The map is the ranked shortlist.
Rain alone never raises the alarm.
Earthquakes are context only. They never move the score.

Open N H 58, kilometre 3.25 to 3.50.
Risk Priority Index eighty-six — Critical.
Moving 6.2 millimetres a month, twice the baseline.
Rain amplifies motion; it is not the hazard by itself.
The outlook is a threshold-crossing window of thirty-five to sixty-four days
if this trend continues — not a failure date.

Trends and History replays sixteen satellite passes from the same data.
Action sites rose from three to seven.
This site climbed from sixty-one to eighty-six.
History is recomputed, so every past score is reproducible.

Now the generative A I.
Gemini does not compute risk. The engine already did that.
Gemini investigates with seven read-only tools.
It reasons over those facts, summarises what is happening,
and creates the inspection ticket —
recommended action and a field checklist.
A guard verifies every millimetre and every day against the tool results.
On this live ticket: six tool calls, seven numbers verified.
Recommendation: dispatch an inspection crew within twenty-four hours.

Built for Google Cloud: Cloud Run, BigQuery-ready storage,
and Vertex A I or A I Studio for Gemini.
Deterministic maths. Tool-grounded narration. Auditable decisions.

TerraSentinel A I — Team Agent Ram.
Review the live demo, this video, and the repository.
Thank you.
'@)
        $s.Dispose()
