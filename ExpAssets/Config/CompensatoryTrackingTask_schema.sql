CREATE TABLE participants (
    id integer primary key autoincrement not null,
    userhash text not null,
    gender text not null,
    age integer not null, 
    handedness text not null,
    created text not null
);

CREATE TABLE trials (
    id integer primary key autoincrement not null,
    participant_id integer not null references participants(id),
    block_num integer not null,
    trial_num integer not null,
    timestamp text not null,
    buffeting_force text not null,
    additional_force text not null,
    net_force text not null,
    user_input text not null,
    target_position text not null,
    displacement text not null,
    rt text not null
);


CREATE TABLE assessments (
	id integer primary key autoincrement not null,
	participant_id text not null,
	trial_num integer not null,
	block_num integer not null,
	timestamp text not null,
	buffeting_force integer not null,
	additional_force integer not null,
	net_force integer not null,
	user_input integer not null,
	displacement integer not null,
	rt integer not null
);

CREATE TABLE frames (
	id integer primary key autoincrement not null,
	participant_id text not null,
	trial_num integer not null,
	block_num integer not null,
	timestamp text not null,
	mean_rt integer not null,
	lapses integer not null,
	samples integer not null
);