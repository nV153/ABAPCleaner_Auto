CLASS z_testclass DEFINITION
  PUBLIC FINAL
  CREATE PUBLIC.

  PUBLIC SECTION.
    METHODS test_method.
ENDCLASS.


CLASS z_testclass IMPLEMENTATION.
  METHOD test_method.
    DATA lv_text TYPE string.
    DATA lv_num  TYPE i.

    lv_text = 'Hello Cleaner'.
    lv_num = 1.

    IF lv_num = 1.
      WRITE lv_text.
    ENDIF.

    IF lv_num = 2.
      WRITE 'unused'.
    ENDIF.
  ENDMETHOD.
ENDCLASS.