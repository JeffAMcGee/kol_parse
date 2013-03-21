
float initiative_with_ml()
{
	int ml = monster_level_adjustment() - current_mcd();
	float init = initiative_modifier();
	if( ml <= 20 )
		return init;
	else if( ml <= 40 )
		return init - (ml - 20);
	else if( ml <= 60 )
		return init - (ml * 2 - 60);
	else if( ml <= 80 )
		return init - (ml * 3 - 120);
	else if( ml <= 100 )
		return init - (ml * 4 - 200);
	else
		return init - (ml * 5 - 300);
}

void main()
{
	string output = "[kol_parse];";
	output += " Muscle="      + to_string( my_basestat( $stat[muscle] ) ) + ";";
	output += " Mysticality=" + to_string( my_basestat( $stat[mysticality] ) ) + ";";
	output += " Moxie="       + to_string( my_basestat( $stat[moxie] ) ) + ";";
	output += " ml="          + to_string( monster_level_adjustment() ) + ";";
	output += " enc="         + to_string( combat_rate_modifier() ) + ";";
	output += " init="        + to_string( initiative_modifier() ) + ";";
	output += " real_init="   + to_string( initiative_with_ml() ) + ";";
	output += " exp="         + to_string( experience_bonus() ) + ";";
	output += " meat="        + to_string( meat_drop_modifier() ) + ";";
	output += " item="        + to_string( item_drop_modifier() ) + ";";
	print( output );
}
