*&---------------------------------------------------------------------*
*& Include z_test_inc
*&---------------------------------------------------------------------*
FORM do_something.
  DATA lv_num TYPE i.

  lv_num = 1.

  IF lv_num = 1.
    WRITE 'ONE'.
  ENDIF.

  IF lv_num = 2.
    WRITE 'TWO'.
  ENDIF.
ENDFORM.