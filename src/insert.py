from collections.abc import Mapping, Sequence, Iterable

from psycopg2 import sql

from query import Query
from base import BaseCommand
from behaviours import WithBehaviour, ReturningBehaviour, TableBehaviour


class Insert(BaseCommand, WithBehaviour, ReturningBehaviour, TableBehaviour):
    """
    Builder for INSERT command.
    Usage examples:
    * Simple array-based construction:
        Insert(conn, table='users', columns=['id', 'name', 'age'], values=[
            [1, 'John', 18],
            [2, 'James', 19],
            [3, 'Jannet', 20],
        ])
            => INSERT INTO "users"("id", "name", "age") VALUES
                (1, 'John', 18), (2, 'James', 19), (3, 'Jannet', 20)
    * Dictionary-based construction (single row):
        Insert(conn, table='users', values={'id': 1, 'name': 'John', 'age': 18})
            => INSERT INTO "users"("id", "name", "age") VALUES (1, 'John', 18)
    * Dictionary-based construction (multiple rows):
        Insert(conn, table='users', values=[
            {'id': 1, 'name': 'John', 'age': 18},
            {'id': 2, 'name': 'James', 'age': 19},
            {'id': 3, 'name': 'Jannet', 'age': 20},
        ])
            => INSERT INTO "users"("id", "name", "age") VALUES
                (1, 'John', 18), (2, 'James', 19), (3, 'Jannet', 20)
    * Generators are supported:
        def get_values():
            yield 1, 'John', 18
            yield 2, 'John', 19
            yield 3, 'Jannet', 20

        Insert(conn, table='users', columns='id, name, age', values=get_values())
            => INSERT INTO "users"("id", "name", "age") VALUES
                (1, 'John', 18), (2, 'James', 19), (3, 'Jannet', 20)
    * Combining with SELECT:
        select = Query(conn).select('*').from_('noobies')
        Insert(conn, table='users', columns='id, name, age', values=select)
            => INSERT INTO "users"("id", "name", "age") SELECT * FROM "noobies"
    """
    def __init__(self, conn, table=None, alias=None, columns=None, values=None):
        super().__init__(conn)
        WithBehaviour.__init__(self, self)
        ReturningBehaviour.__init__(self, self)
        TableBehaviour.__init__(self, self, table, alias)
        self._columns = []
        if columns is not None:
            self.columns(columns)
        self._values = None
        if values is not None:
            self.values(values)
        self._conflict = False
        self._conflict_constraint = None
        self._conflict_action = None

    def columns(self, fields):
        """
        Sets a columnt list for the query.
        Usage examples:
        * Coma-separated string:
            columns('id, name')
        * Iterable object:
            columns(['id', 'name'])
        :param fields:
        :return: self
        """
        self._columns = []
        self.add_columns(fields)
        return self

    def add_columns(self, fields):
        """
        Adds a new column to the query.
        See `columns` method for examples
        :param fields:
        :return: self
        """
        if isinstance(fields, str):
            fields = fields.split(',')
        self._columns.extend([field.strip() for field in fields])
        return self

    def values(self, values):
        """
        Sets the VALUES query block. It support several types of values: Query, dict, list, generator etc.
        Please check out the examples in the class docs
        :param values: the values to insert
        :return: self
        """
        if isinstance(values, BaseCommand):
            self._values = values
        elif isinstance(values, Mapping):
            self._values = []
            self.add_values(values)
        elif isinstance(values, Iterable):
            self._values = []
            for vs in values:
                self.add_values(vs)
        else:
            raise Exception('Unsupported values type')
        return self

    def add_values(self, values):
        """
        Adds a new values to the VALUES query block. It support several types of values: Query, dict, list, generator etc.
        Please check out the examples in the class docs
        :param values: the values to insert
        :return: self
        """
        if isinstance(values, BaseCommand):
            raise Exception('Adding SELECT is not supported. Please call `values` method instead')
        elif isinstance(values, Mapping):
            for field in values.keys():
                if field not in self._columns:
                    self._columns.append(field)
            self._values.append(values)
        elif isinstance(values, Sequence):
            if len(self._columns) == 0:
                raise Exception('Please specify column names')
            row = {}
            i = 0
            for column in self._columns:
                row[column] = values[i]
                i += 1
            self._values.append(row)
        else:
            raise Exception('Unsupported values type')
        return self

    def on_conflict_do_nothing(self, constraint=None):
        """
        Sets ON CONFLICT query block with DO NOTHING action
        Example:
            on_conflict_do_nothing('id')
                => ON CONFLICT ("id") DO NOTHING
        :param constraint: defines the conflicting constraint
        :return: self
        """
        self.on_conflict_do_update(constraint, None)
        return self

    def on_conflict_do_update(self, constraint, action):
        """
        Sets ON CONFLICT query block with DO UPDATE action.
        When `action` is None, this method works as `on_conflict_do_nothing`.
        Example:
            on_conflict_do_update('id', {
                'last_name': expr('excluded.last_name'), # This won't be escaped because of `expr` type
                'first_name': '; drop database; --',  # This will be escaped, default behaviour
                'id': 7,
                'age': None,
            })
                => ON CONFLICT ("id") DO UPDATE SET "last_name"="excluded"."last_name", "first_name"='; drop database; --',
                        "id"=7, "age"=null
        :param constraint: defines the conflicting constraint
        :param action: dictionary for SET block
        :return: self
        """
        self._conflict = True
        self._conflict_constraint = constraint
        self._conflict_action = action
        return self

    def _build_query(self, param_name_prefix=None):
        super()._build_query(param_name_prefix)
        parts = [
            self._build_query_with(),
            self._build_query_insert_into(),
            self._build_query_values(),
            self._build_query_on_conflict(),
            self._build_query_returning(),
        ]
        res = sql.SQL(' ').join([p for p in parts if p is not None])
        return res

    def _build_query_insert_into(self):
        if not self._table:
            return None
        res = sql.SQL('INSERT INTO ') + self._quote_table(self._table)
        if len(self._columns) > 0:
            res += sql.SQL('({})').format(sql.SQL(', ').join(
                [self._quote_string(x) for x in self._columns]
            ))
        return res

    def _build_query_values(self):
        if isinstance(self._values, BaseCommand):
            return self._build_subquery(self._values)
        elif isinstance(self._values, Iterable):
            res = []
            for vs in self._values:
                row = []
                for column in self._columns:
                    if column in vs:
                        value = vs[column]
                        if isinstance(value, Query):
                            row.append(sql.SQL('(') + self._build_subquery(value) + sql.SQL(')'))
                        else:
                            row.append(self._set_param(value, json_stringify=True))
                    else:
                        row.append(sql.Literal(None))
                res.append(sql.SQL('({})').format(sql.SQL(', ').join(row)))
            if len(res) == 0:
                return None
            return sql.SQL('VALUES ') + (sql.SQL(', ').join(res))
        return None

    def _build_query_on_conflict(self):
        if not self._conflict:
            return None
        res = sql.SQL('ON CONFLICT')
        if self._conflict_constraint:
            res += sql.SQL(' ({})').format(self._quote_string(self._conflict_constraint))
        if self._conflict_action is not None:
            items = []
            for field, val in self._conflict_action.items():
                items.append(sql.SQL('{field}={value}').format(
                    field=self._quote_string(field),
                    value=self._place_value(val),
                ))
            res += sql.SQL(' DO UPDATE SET ') + (sql.SQL(', ').join(items))
        else:
            res += sql.SQL(' DO NOTHING')
        return res