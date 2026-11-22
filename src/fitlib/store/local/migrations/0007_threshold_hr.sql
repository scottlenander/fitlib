-- Threshold heart rate (lactate threshold HR) in the athlete history, for heart-rate TSS on
-- rides without power. NULL means "unchanged by this entry", like the other values.
ALTER TABLE athlete_history ADD COLUMN threshold_hr INTEGER;
