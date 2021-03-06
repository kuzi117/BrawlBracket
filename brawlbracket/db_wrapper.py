from brawlbracket.util import KeySingleton
#import logger

import sqlite3
import os
import uuid
import json

class DBWrapper(metaclass=KeySingleton):
    """
    Class to wrap an SQLite db.
    
    This class only defines useful methods for interacting with the
    database. Ways to use these methods must be defined elsewhere.

    name should be the database name excluding '.db'
    """
    
    def __init__(self, name, **args):
        # Create db filepath
        self.filepath = args.get('filepath', 'file') + os.path.sep
        if not os.path.exists(self.filepath):
            os.makedirs(self.filepath)

        self.name = name
        self.conn = \
            lambda: sqlite3.connect(self.filepath + os.path.sep + name + '.db',
                                    detect_types=sqlite3.PARSE_DECLTYPES)

        # Add converter for bool
        sqlite3.register_adapter(bool, int)
        sqlite3.register_converter('BOOLEAN', lambda v: bool(int(v)))
        
        # Add converter for UUID
        sqlite3.register_adapter(uuid.UUID, str)
        sqlite3.register_converter(
            'UUID', 
            lambda v: uuid.UUID(str(v, 'utf-8')) if v != b'None' else None
            )
        
        # Add converter for list of UUIDs
        # No adapter because it's impossible to tell sqlite3 we only want to
        # handle lists of UUIDs
        def _uuid_list_convert(l):
            l = json.loads(str(l, 'utf-8'))
            rv = []
            for x in l:
                if x is None:
                    rv.append(None)
                else:
                    rv.append(uuid.UUID(x))
            return rv
        sqlite3.register_converter('UUIDLIST', _uuid_list_convert)

        # Logger
        #self.log = logger.Logger()
    
    def exit(self):
        """
        Prepares for exit.
        """
        #self.log.log('Closing {} db.'.format(self.name))

        # Used to have a single instance of connection, now threads generate
        # their own connections
        #self.conn.close()
        pass
        
    def table_exists(self, table_name):
        """
        Returns whether or not a table exists in the database.
        """
        # Prep the statement and symbols
        stmt = ('SELECT name '
                'FROM sqlite_master '
                'WHERE type=\'table\' AND name=?;')
        symbols = (table_name,)
        
        # Get DB cursor
        conn = self.conn()
        curs = conn.cursor()
        
        # Get results
        curs.execute(stmt, symbols)
        one = curs.fetchone()
        curs.close()
        conn.close()
        
        if one is not None:
            return True
        else:
            return False
    
    def column_exists(self, table_name, row_name):
        """
        Returns whether or not a column exists in a table.
        """
        # Prep statement and symbols
        stmt = ('SELECT ? '
                'FROM ? ')
        symbols = (table_name, row_name)
        
        # Get DB cursor
        conn = self.conn()
        curs = conn.cursor()
        
        # Get results
        curs.execute(stmt, symbols)
        one = curs.fetchone()
        curs.close()
        conn.close()
        
        if one is not None:
            return True
        else:
            return False

    def create_table(self, name, field_names, field_types, primary_name):
        """
        Creates a table.
        
        Doesn't do fancy injection prevention because table names can't
        be paramaterized.
        """
        # Ensure that all fields are typed
        if len(field_types) != len(field_names):
            raise AssertionError('Field types length doesn\'t match '
                                 ' field names length!\n{}\n{}'.format(field_types, field_names))
        # Ensure that primary field is there
        elif False in [(x in field_names) for x in primary_name.split(', ')]:
            raise AssertionError('Primary name not in field names!')
        
        # Create statment
        stmt = ('CREATE TABLE {} ('
                '{}'
                'PRIMARY KEY ({}))')

        # Format the table name, field format spaces and primary name
        stmt = stmt.format(name,
                           '{} {},' * len(field_names),
                           primary_name)
        
        # Create symbols list for formatting
        symbols = []
        
        for i in range(len(field_names)):
            symbols += [field_names[i], field_types[i]]
        
        # Format the field names and types
        stmt = stmt.format(*symbols)

        #self.log.log('Create statement: {}'.format(stmt))
        
        conn = self.conn()
        curs = conn.cursor()
        
        curs.execute(stmt)
        
        conn.commit()
        curs.close()
        conn.close()
    
    def select_values(self, table, col_names, conditions, unsafe = None):
        """
        Selects values from a table.
        Col_names is a list of strings that name a column in the table (these
        should be sql-safe though I'm not quite sure how they couldn't be.
        Conditions is a list of strings already in the form of a valid
        SQL condition (e.g. "col_name = 100"). These should be sql-safe (i.e.
        generated by you and known to not contain sql injects).
        Unsafe are unsafe conditions that need to be checked for safety.
        """
        col_str = ', '.join(['{}'] * len(col_names)).format(*col_names)
        if conditions or unsafe:
            num_conds = 0
            if conditions:
                num_conds += len(conditions)
            if unsafe:
                num_conds += len(unsafe)
            
            cond_str = ' AND '.join(['{}'] * num_conds)
            
            # Format column names, table name, and conditions format string
            stmt = ('SELECT {} '
                    'FROM {} '
                    'WHERE {}').format(col_str, table, cond_str)
            
            # Generate list of items to format into conditions format string
            final_conds = []
            if conditions:
                final_conds.extend(conditions)
            if unsafe:
                final_conds.extend(['?'] * len(unsafe))
            
            # Format in safe conditions and symbol for unsafe conditions
            stmt = stmt.format(*final_conds)
            
        else:
            # Format table name and condition format string
            stmt = ('SELECT {} '
                    'FROM {}').format(col_str, table)

        # Build list that will be used to as values for statement execution
        symbol_list = []
        if unsafe:
            symbol_list.extend(unsafe)
        
        #self.log.log('Select statement: {}'.format(stmt))
        #print('Select statement: {}, {}'
        #    .format(stmt, stmt.replace('?', '{}').format(*symbol_list)))
        
        # Get cursor and execute the statement
        conn = self.conn()
        curs = conn.cursor()
        curs.execute(stmt, symbol_list)
        
        # Return all results
        rows = curs.fetchall()
        curs.close()
        conn.close()
        
        return rows
    
    def insert_values(self, table, values, ignore=False):
        """
        Inserts values into a table.
        
        Values is a list of tuples of the values for each row.
        """
        temp_strs = []
        for val in values:
            # Create and format the string for each set of values to
            # insert
            val_str = '(' + ', '.join('?' * len(val)) + ')'
            
            # Append to list of sets of values
            temp_strs.append(val_str)
        
        vals_str = ', '.join(temp_strs) # Drop the last ', '

        if ignore:
            stmt = ('INSERT OR IGNORE INTO {} '
                    'VALUES {}').format(table, vals_str)
        else:
            stmt = ('INSERT OR REPLACE INTO {} '
                    'VALUES {}').format(table, vals_str)
                    
        # Build list that will be used to as symbols for statement execution
        symbol_list = []
        for v in values:
            symbol_list.extend(v)
        
        #self.log.log('Insert statement: {}'.format(stmt))
        #print('Insert statement: {}'
        #    .format(stmt.replace('?', '{}').format(*symbol_list)))
        
        # Execute the statement
        conn = self.conn()
        curs = conn.cursor()
        curs.execute(stmt, symbol_list)
        conn.commit()
        curs.close()
        conn.close()

    def delete_values(self, table, conditions):
        """
        Deletes values from table using conditions
        
        This is potentially unsafe. Please consider your conditions and whether
        or not they could have bad values in them.
        """
        
        if conditions:
            cond_str = '{}' + ' AND {}' * (len(conditions) - 1)
            
            # Format table name and extra format strings
            stmt = ('DELETE FROM {} '
                    'WHERE {}').format(table, cond_str)
            
            # Format the conditions into the new format string
            stmt = stmt.format(*conditions)
            
        else:
            # Format table name format string
            stmt = 'DELETE FROM {}'.format(table)

        #self.log.log('Delete statement: {}'.format(stmt))
        
        # Get cursor and execute the statement
        conn = self.conn()
        curs = conn.cursor()
        curs.execute(stmt)
        
        # Commit
        conn.commit()
        curs.close()
        conn.close()
