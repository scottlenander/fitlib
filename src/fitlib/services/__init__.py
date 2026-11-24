"""The tasks the web app and the command line share.

Each service takes the library's stores, does one thing a person asks for (list rides, edit
them, compare them...) and returns plain results. The API and the CLI only read their input,
call a service, and show what comes back, so both behave the same.

Services raise ``ServiceError`` (see ``errors``) for requests a person can fix; the API turns
it into a 422 and the CLI into an error message.
"""
