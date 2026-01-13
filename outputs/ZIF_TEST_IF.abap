INTERFACE zif_test_if


  PUBLIC.
  CONSTANTS c_ok   TYPE i VALUE 1.
  CONSTANTS c_fail TYPE i VALUE 0.

  TYPES:
    BEGIN OF ty_data,
      id   TYPE i,
      text TYPE string,
    END OF ty_data.


  METHODS get_data
    IMPORTING iv_id          TYPE i
    RETURNING VALUE(rs_data) TYPE ty_data.

ENDINTERFACE.