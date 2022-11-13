from psycopg2 import sql

from base import BaseCommand
from behaviours import WhereBehaviour, WithBehaviour, FromBehaviour, ReturningBehaviour


class Delete(BaseCommand, WhereBehaviour, WithBehaviour, FromBehaviour, ReturningBehaviour):
    """
    Builder for DELETE command.
    Examples:
        1) q = Delete(conn, 'users', (WHERE_OP_NOT, 'active')).returning('id')
            for id in q.column():
                print(id)
        It builds the following query:
            DELETE FROM "users" WHERE NOT "active" RETURNING "id"

        2) Another way to build the same query:
            q = Delete(conn).from_('users').where([WHERE_OP_NOT, 'active']).returning('id')
    """
    def __init__(self, conn, from_=None, alias=None, where=None):
        super().__init__(conn)
        WhereBehaviour.__init__(self, self)
        WithBehaviour.__init__(self, self)
        FromBehaviour.__init__(self, self)
        ReturningBehaviour.__init__(self, self)
        if from_ is not None:
            self.from_(from_, alias)
        if where is not None:
            self.where(where)

    def _build_query(self, param_name_prefix=None):
        super()._build_query(param_name_prefix)
        parts = [
            self._build_query_with(),
            sql.SQL('DELETE'),
            self._build_query_from(),
            self._build_query_where(),
            self._build_query_returning(),
        ]
        res = sql.SQL(' ').join([p for p in parts if p is not None])
        return res

    def _build_query_where(self):
        incorrect_where = False
        if self._where in [None]:
            incorrect_where = True
        if incorrect_where:
            raise Exception('Sorry empty WHERE block is restricted on DELETE operations for security reasons')
        return super()._build_query_where()