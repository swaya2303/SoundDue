% reasoning/rules/base.metta
%
% SoundDue base MeTTa rules.
%
% EXPERIMENTAL: Hyperon / MeTTa is an experimental runtime.
% See docs/reasoning-runtime.md.
%
% Fact schema (all string atoms -- produced by reasoning/facts.py):
%
%   (verified-mapping <recording_id> <work_id> <source_label>)
%
%   (claim <work_id> <contributor> <share_str> <rights_category>
%          <territory> <effective_from> <effective_to> <share_convention>)
%       share_str is an exact decimal string, e.g. "60.0000"
%
%   (unclaimed <work_id> <share_str> <rights_category>
%              <territory> <effective_from> <effective_to>)
%
%   (scope-compatible <work_id_a> <work_id_b>
%                     <rights_category> <territory>
%                     <effective_from> <effective_to>)
%       Computed in Python (see facts.py) -- not inferred here.
%
% ---------------------------------------------------------------------------
% Convenience derivation: a recording has a link if there is a verified mapping
% ---------------------------------------------------------------------------

(= (has-link $r)
   (match &self (verified-mapping $r $w $s) True))

% ---------------------------------------------------------------------------
% A claim exists for a work
% ---------------------------------------------------------------------------

(= (work-has-claim $w)
   (match &self (claim $w $c $sh $rc $t $ef $et $sc) True))
