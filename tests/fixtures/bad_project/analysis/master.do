cd "/Users/researcher/project"
use "data/working.csv", clear
merge 1:1 firm_id year using "data/other_a.dta"
merge 1:1 firm_id year using "data/other_b.dta"
save "output/final_sample.dta", replace
